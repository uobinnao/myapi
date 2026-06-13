from importlib import import_module

MODEL_MODULES: tuple[str, ...] = ("app.features.foods.model",)


def import_all_models() -> None:
    """Import all SQLAlchemy model modules so they register with Base.metadata."""
    for module_name in MODEL_MODULES:
        import_module(module_name)
