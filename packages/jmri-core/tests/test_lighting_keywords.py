import pytest

from jmri_core.constants.lighting import is_light_label


@pytest.mark.parametrize(
    "label",
    [
        "Lumières avant",
        "Lumières cabine",
        "Lumières arrière",
        "lumiere",
        "LUMIERE",
        "Feu rouge",
        "Lampe de poche",
        "Phare avant",
        "Headlight",
        "Front light",
        "Cabin lamp",
        "  Lumières avant  ",
    ],
)
def test_is_light_label_matches_known_keywords(label):
    assert is_light_label(label) is True


@pytest.mark.parametrize(
    "label",
    [
        "Horn",
        "Klaxon",
        "Coupler",
        "Bell",
        "Sifflet",
        "Attelage",
        "",
        None,
    ],
)
def test_is_light_label_rejects_non_light_labels(label):
    assert is_light_label(label) is False
