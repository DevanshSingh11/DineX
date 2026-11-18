import httpx
from dinex.assistant import answer
from dinex.config import Config
from pathlib import Path


def test_remote_ranker_discards_unknown_ids_and_prose(monkeypatch):
    cfg = Config(
        Path("unused"),
        "s" * 40,
        ai_url="https://provider.example.test",
        ai_key="test",
        ai_model="test",
    )
    items = [
        {
            "id": 4,
            "name": "Herb plate",
            "dietary": "vegan",
            "ingredients": "Mint",
            "description": "",
            "available": True,
            "featured": False,
            "price": 123,
        },
        {
            "id": 5,
            "name": "Unavailable",
            "dietary": "vegan",
            "ingredients": "",
            "description": "",
            "available": False,
            "featured": False,
            "price": 2,
        },
    ]

    def reply(url, **options):
        assert "Unavailable" not in str(options["json"]) and "api_key" not in str(
            options["json"]
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[999, 5, 4, 4]"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", reply)
    result = answer(cfg, "Vegan dishes", {"items": items})
    assert result["mode"] == "AI provider" and [i["id"] for i in result["items"]] == [4]

    def offline(*args, **kwargs):
        raise httpx.ConnectError("test provider offline")

    monkeypatch.setattr(httpx, "post", offline)
    result = answer(cfg, "Vegan dishes", {"items": items})
    assert (
        "provider unavailable" in result["mode"] and result["items"][0]["price"] == 123
    )
