"""Catalog & Inventory microservice package for PulseMesh."""

from services.catalog.app import create_catalog_app
from services.catalog.inventory import InventoryEngine
from services.catalog.models import CatalogModel

__all__ = ["create_catalog_app", "CatalogModel", "InventoryEngine"]
