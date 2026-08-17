from integrations.astrbot_plugin_chat_insight.outbox import Outbox


def test_outbox_survives_reopen(tmp_path):
    path = tmp_path / "outbox.db"
    Outbox(path).enqueue({"external_message_id": "001"})
    reopened = Outbox(path)
    batch = reopened.peek()
    assert batch[0][1]["external_message_id"] == "001"
    reopened.delete([batch[0][0]])
    assert reopened.count() == 0
