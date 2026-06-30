def test_fred_weekly_regime_pipeline_imports() -> None:
    import src.signalforge.engines.regime.fred_weekly_pipeline  # noqa: F401


def test_fred_weekly_regime_pipeline_cli_imports() -> None:
    import src.signalforge.engines.regime.fred_weekly_regime_pipeline_cli  # noqa: F401


def test_regime_to_alignment_to_eligibility_import_chain() -> None:
    import src.signalforge.engines.regime.fred_weekly_pipeline  # noqa: F401
    import src.signalforge.engines.alignment.regime_asset_options_alignment  # noqa: F401
    import src.signalforge.engines.strategy_selection.strategy_family_eligibility  # noqa: F401

