from pathlib import Path

from newsflow.services.news_publisher import NewsPublisher


def test_image_probability_is_deterministic(monkeypatch):
    publisher = NewsPublisher()
    monkeypatch.setattr(publisher.settings, "news_image_percent", 40)
    assert publisher.should_generate_image(12345) == publisher.should_generate_image(12345)


def test_image_probability_can_be_disabled(monkeypatch):
    publisher = NewsPublisher()
    monkeypatch.setattr(publisher.settings, "news_image_percent", 0)
    assert publisher.should_generate_image(1) is False


def test_image_probability_can_be_full(monkeypatch):
    publisher = NewsPublisher()
    monkeypatch.setattr(publisher.settings, "news_image_percent", 100)
    assert publisher.should_generate_image(1) is True
