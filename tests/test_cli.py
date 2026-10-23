import json

from nutriscore.cli import main


def test_manual_json_user_case(capsys):
    main(["manual", "--categoria", "general", "--energia-kj", "1762", "--azucares", "13.9",
          "--saturadas", "0", "--sal", "6.81", "--proteinas", "7.2", "--fvl", "0", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["letra"] == "E"
    assert out["puntuacion_rango"] == [23, 28]
    assert out["fuente"] == "manual"
    assert [d["campo"] for d in out["datos_faltantes"]] == ["fibra"]


def test_manual_text_shows_range_when_letter_uncertain(capsys):
    main(["manual", "--categoria", "general", "--energia-kj", "900", "--azucares", "5",
          "--saturadas", "1", "--proteinas", "3", "--fibra", "2", "--fvl", "0"])
    out = capsys.readouterr().out
    assert "entre" in out and "sal" in out
