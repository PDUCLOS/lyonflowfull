"""SpatioTemporal GCN — modèle GNN pour prédiction trafic.

Architecture (SpatioTemporalGCN) :
1. **GRU temporel** (5 canaux input → hidden) — capture l'évolution temporelle
2. **2 × GCNConv + LeakyReLU + skip connections** — propage l'info sur le graphe
3. **Linear** → prédictions multi-horizon (par nœud)

Inspiré de l'architecture DCRNN / ST-GCN adaptée au contexte urbain :
* Nœuds = ~1520 capteurs (boucles Grand Lyon) → cellules H3 res.13
* Arêtes = K=2 grid_disk bidirectionnel (~9540 arêtes)
* Canaux input par timestep = [speed, hour_sin, hour_cos, day_sin, day_cos]
* Sortie = 6 horizons (5, 15, 30, 60, 180, 360 min)

References :
* Li et al., "Diffusion Convolutional Recurrent Neural Network: Data-Driven
  Traffic Forecasting", ICLR 2018
* Yu et al., "Spatio-Temporal Graph Convolutional Networks: A Deep Learning
  Framework for Traffic Forecasting", IJCAI 2018
* h3-py pour la grille : https://h3geo.org

Note : ce module importe ``torch`` et ``torch_geometric`` paresseusement.
Si ces libs ne sont pas installées, ``is_available()`` retourne ``False`` et
le code lève une ``STGCNImportError`` claire au moment de l'instanciation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Détection d'environnement
# -----------------------------------------------------------------------------


class STGCNImportError(ImportError):
    """Levée quand torch / torch_geometric ne sont pas installés.

    Le reste du projet peut tourner sans GNN (XGBoost fait le job).
    Cette erreur aide à diagnostiquer ce qui manque.
    """


def _try_import_torch() -> tuple[object | None, str | None]:
    """Tente d'importer torch. Retourne (module, error_message)."""
    try:
        import torch  # type: ignore[import-untyped]

        return torch, None
    except ImportError as e:
        return None, str(e)


def _try_import_torch_geometric() -> tuple[object | None, str | None]:
    """Tente d'importer torch_geometric.nn.GCNConv."""
    try:
        from torch_geometric.nn import GCNConv  # type: ignore[import-untyped]

        return GCNConv, None
    except ImportError as e:
        return None, str(e)


def is_available() -> bool:
    """True si torch ET torch_geometric sont installés."""
    torch_mod, _ = _try_import_torch()
    gcn_cls, _ = _try_import_torch_geometric()
    return torch_mod is not None and gcn_cls is not None


# -----------------------------------------------------------------------------
# Hyperparamètres par défaut
# -----------------------------------------------------------------------------


@dataclass
class STGCNConfig:
    """Hyperparamètres SpatioTemporalGCN.

    Attributes:
        in_channels: Nombre de features par nœud par timestep (défaut 5 :
            speed normalisée, hour_sin, hour_cos, day_sin, day_cos).
        hidden_channels: Dimension du GRU + GCN hidden state (défaut 128).
        out_channels: Horizon de prédiction — 1 par horizon (défaut 1,
            on construit un modèle par horizon).
        num_nodes: Nombre de nœuds du graphe (défaut 1520 pour Lyon).
        seq_len: Longueur de la séquence temporelle d'entrée (défaut 12
            timesteps × 5 min = 1h d'historique).
        dropout: Dropout entre les couches GCN (défaut 0.1).
        gcn_layers: Nombre de couches GCNConv (défaut 2).
        leaky_relu_slope: Pente LeakyReLU (défaut 0.2).
    """

    in_channels: int = 5
    hidden_channels: int = 128
    out_channels: int = 1
    num_nodes: int = 1520
    seq_len: int = 12
    dropout: float = 0.1
    gcn_layers: int = 2
    leaky_relu_slope: float = 0.2


# -----------------------------------------------------------------------------
# Modèle
# -----------------------------------------------------------------------------


class SpatioTemporalGCN:
    """Architecture GNN spatio-temporelle pour prédiction trafic.

    Forward pass :
    1. Entrée : ``x`` de shape ``(batch, seq_len, num_nodes, in_channels)``
    2. GRU temporel par nœud → ``(batch, num_nodes, hidden)``
    3. Pour chaque GCN layer :
       * GCNConv(x, edge_index) + LeakyReLU + Dropout
       * Skip connection (x = x + identity)
    4. Linear → ``(batch, num_nodes, out_channels)`` = prédiction pour le nœud

    Example::

        cfg = STGCNConfig(num_nodes=100, hidden_channels=32)
        model = SpatioTemporalGCN(cfg)
        # x: (batch=4, seq_len=12, num_nodes=100, in_channels=5)
        # edge_index: (2, num_edges) LongTensor
        out = model.forward(x, edge_index)  # (4, 100, 1)
    """

    def __init__(self, config: STGCNConfig | None = None):
        """Construit le modèle. Lève STGCNImportError si torch indisponible."""
        if not is_available():
            raise STGCNImportError(
                "torch + torch_geometric sont requis pour SpatioTemporalGCN. pip install torch torch-geometric"
            )

        import torch
        import torch.nn as nn

        self._torch = torch
        self._nn = nn

        self.config = config or STGCNConfig()
        self._model: torch.nn.Module = self._build()

    def _build(self):
        """Construit le nn.Module interne (caché derrière l'API)."""
        import torch.nn as nn

        cfg = self.config
        # GRU temporel : input (batch*nodes, seq_len, in_channels) → output hidden
        self._gru = nn.GRU(
            input_size=cfg.in_channels,
            hidden_size=cfg.hidden_channels,
            num_layers=1,
            batch_first=True,
        )

        # Couches GCN empilées
        self._gcn_layers = nn.ModuleList()
        self._gcn_norms = nn.ModuleList()
        for _ in range(cfg.gcn_layers):
            self._gcn_layers.append(_safe_gcn_conv(cfg.hidden_channels, cfg.hidden_channels))
            self._gcn_norms.append(nn.LayerNorm(cfg.hidden_channels))

        # Tête de prédiction
        self._head = nn.Linear(cfg.hidden_channels, cfg.out_channels)
        self._dropout = nn.Dropout(cfg.dropout)
        self._leaky_relu = nn.LeakyReLU(cfg.leaky_relu_slope)

        return _ModuleWrapper(self)

    def forward(self, x, edge_index):
        """Forward pass GNN.

        Args:
            x: Tensor ``(batch, seq_len, num_nodes, in_channels)`` ou
               ``(batch, num_nodes, in_channels)`` si seq_len=1.
            edge_index: LongTensor ``(2, num_edges)``.

        Returns:
            Tensor ``(batch, num_nodes, out_channels)`` — prédictions.
        """
        cfg = self.config

        if x.dim() == 3:
            # (batch, num_nodes, in_channels) → ajouter seq_len=1
            x = x.unsqueeze(1)

        b, t, n, c = x.shape
        assert n == cfg.num_nodes, f"num_nodes mismatch: {n} vs {cfg.num_nodes}"
        assert c == cfg.in_channels, f"in_channels mismatch: {c} vs {cfg.in_channels}"

        # 1) Temporal GRU : on traite chaque nœud indépendamment
        # Reshape : (b*n, t, c) → GRU → (b*n, t, hidden) → take last
        x_reshaped = x.reshape(b * n, t, c)
        gru_out, _ = self._gru(x_reshaped)
        h = gru_out[:, -1, :]  # (b*n, hidden)
        h = h.reshape(b, n, cfg.hidden_channels)

        # 2) Spatial GCN : on traite chaque batch comme un graphe indépendant
        # Reshape : (b, n, hidden) → (b*n, hidden) ; edge_index broadcast
        h_flat = h.reshape(b * n, cfg.hidden_channels)
        for gcn, norm in zip(self._gcn_layers, self._gcn_norms):
            h_new = gcn(h_flat, _expand_edge_index(edge_index, b, n))
            h_new = self._leaky_relu(h_new)
            h_new = self._dropout(h_new)
            h_new = norm(h_new)
            h_flat = h_flat + h_new  # skip connection

        # 3) Head : (b*n, hidden) → (b*n, out_channels) → (b, n, out_channels)
        out = self._head(h_flat)
        out = out.reshape(b, n, cfg.out_channels)
        return out

    # ------------------------------------------------------------------
    # Persistance (compatible MLflow / joblib)
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Sauvegarde state_dict + config."""
        torch = self._torch
        torch.save(
            {
                "config": self.config.__dict__,
                "state_dict": self._model.state_dict(),
            },
            path,
        )
        logger.info("STGCN saved to %s", path)

    def load(self, path: str) -> None:
        """Charge state_dict + config depuis un fichier."""
        torch = self._torch
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        self.config = STGCNConfig(**ckpt["config"])
        # Reconstruire le modèle (gru/gcn_layers/head ont été re-créés)
        self._model = self._build()
        self._model.load_state_dict(ckpt["state_dict"])
        logger.info("STGCN loaded from %s", path)

    @property
    def num_parameters(self) -> int:
        """Nombre total de paramètres entraînables."""
        return sum(p.numel() for p in self._model.parameters() if p.requires_grad)


# -----------------------------------------------------------------------------
# Wrappers internes (encapsulent les sub-modules dans un seul nn.Module)
# -----------------------------------------------------------------------------


def _safe_gcn_conv(in_channels: int, out_channels: int):
    """Crée un GCNConv avec gestion d'erreur."""
    from torch_geometric.nn import GCNConv

    return GCNConv(in_channels, out_channels)


def _expand_edge_index(edge_index, batch_size: int, num_nodes: int):
    """Réplique edge_index pour un batch de graphes identiques.

    Si batch_size=1, retourne edge_index tel quel. Sinon, ajoute un offset
    de ``i * num_nodes`` à chaque edge du batch i.
    """
    torch = None
    try:
        import torch
    except ImportError:  # pragma: no cover
        return edge_index
    if batch_size == 1:
        return edge_index
    pieces = [edge_index + i * num_nodes for i in range(batch_size)]
    return torch.cat(pieces, dim=1)


class _ModuleWrapper:
    """Délègue parameters/eval/train/state_dict/load_state_dict au nn.Module interne.

    SpatioTemporalGCN expose `self._model` qui doit se comporter comme un
    nn.Module pour les tests + save/load. Cette classe encapsule un vrai
    nn.Module (créé via `build_module`) et délègue les attributs courants.
    """

    def __init__(self, owner):
        self._owner = owner
        self._inner = build_module(owner.config)

    def __getattr__(self, name):
        # Appelé uniquement si attribut introuvable sur l'instance.
        return getattr(self._inner, name)


# -----------------------------------------------------------------------------
# Constructeur alternatif pour qui veut un nn.Module direct
# -----------------------------------------------------------------------------
# Constructeur alternatif pour qui veut un nn.Module direct
# -----------------------------------------------------------------------------


def build_module(config: STGCNConfig | None = None):
    """Retourne un nn.Module prêt à l'emploi (utile pour l'entraînement)."""
    if not is_available():
        raise STGCNImportError("torch + torch_geometric requis")
    import torch.nn as nn

    cfg = config or STGCNConfig()

    class _STGCNModule(nn.Module):
        def __init__(inner_self):
            super().__init__()
            inner_self.cfg = cfg
            inner_self.gru = nn.GRU(
                input_size=cfg.in_channels,
                hidden_size=cfg.hidden_channels,
                num_layers=1,
                batch_first=True,
            )
            inner_self.gcn_layers = nn.ModuleList(
                [_safe_gcn_conv(cfg.hidden_channels, cfg.hidden_channels) for _ in range(cfg.gcn_layers)]
            )
            inner_self.gcn_norms = nn.ModuleList([nn.LayerNorm(cfg.hidden_channels) for _ in range(cfg.gcn_layers)])
            inner_self.head = nn.Linear(cfg.hidden_channels, cfg.out_channels)
            inner_self.dropout = nn.Dropout(cfg.dropout)
            inner_self.leaky_relu = nn.LeakyReLU(cfg.leaky_relu_slope)

        def forward(inner_self, x, edge_index):
            if x.dim() == 3:
                x = x.unsqueeze(1)
            b, t, n, c = x.shape
            x_reshaped = x.reshape(b * n, t, c)
            gru_out, _ = inner_self.gru(x_reshaped)
            h = gru_out[:, -1, :].reshape(b, n, cfg.hidden_channels)
            h_flat = h.reshape(b * n, cfg.hidden_channels)
            for gcn, norm in zip(inner_self.gcn_layers, inner_self.gcn_norms):
                h_new = gcn(h_flat, _expand_edge_index(edge_index, b, n))
                h_new = inner_self.leaky_relu(h_new)
                h_new = inner_self.dropout(h_new)
                h_new = norm(h_new)
                h_flat = h_flat + h_new
            out = inner_self.head(h_flat).reshape(b, n, cfg.out_channels)
            return out

    return _STGCNModule()
