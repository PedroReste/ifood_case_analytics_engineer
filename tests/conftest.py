"""Configuração compartilhada da suíte de contratos do case."""

from __future__ import annotations

import sys
from pathlib import Path


# Permite executar `pytest` sem depender de instalação editável do pacote.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
