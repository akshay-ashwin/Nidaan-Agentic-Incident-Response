import config


def test_model_name_is_single_nonpreview_flash():
    assert "flash" in config.MODEL_NAME
    assert "preview" not in config.MODEL_NAME


def test_temperature_zero():
    assert config.TEMPERATURE == 0
