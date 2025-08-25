from apps.hydrochat.enums import Intent, PendingAction, ConfirmationType, DownloadStage
from apps.hydrochat.utils import validate_nric, mask_nric
from apps.hydrochat.config import load_config


def test_enums_basic():
    assert Intent.CREATE_PATIENT.name == 'CREATE_PATIENT'
    assert PendingAction.NONE.name == 'NONE'
    assert ConfirmationType.NONE.name == 'NONE'
    assert DownloadStage.NONE.name == 'NONE'


def test_nric_masking():
    masked = mask_nric('S1234567A')
    assert masked.startswith('S') and masked.endswith('7A') and '******' in masked


def test_nric_validation():
    assert validate_nric('S1234567A') is True
    assert validate_nric('1234567A') is False


def test_config_snapshot_redaction(monkeypatch):
    monkeypatch.setenv('HYDRO_BASE_URL', 'http://x')
    monkeypatch.setenv('HYDRO_AUTH_TOKEN', 'ABCDSECRET')
    cfg = load_config()
    snap = cfg.snapshot()
    assert snap['auth_token'].startswith('ABCD') and snap['auth_token'].endswith('***')
