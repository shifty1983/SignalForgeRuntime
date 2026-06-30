def test_regime_asset_options_alignment_cli_imports() -> None:
    import src.alignment.regime_asset_options_alignment_cli  # noqa: F401


def test_regime_asset_options_alignment_file_writer_imports() -> None:
    import src.alignment.regime_asset_options_alignment_file_writer  # noqa: F401


def test_alignment_to_eligibility_import_chain() -> None:
    import src.alignment.regime_asset_options_alignment  # noqa: F401
    import src.strategy_selection.strategy_family_eligibility  # noqa: F401
