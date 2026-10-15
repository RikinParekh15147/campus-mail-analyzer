from campusmail.store import Store
from campusmail.personalization import Personalizer


def test_robotics_feedback_does_not_raise_unrelated_workshops(tmp_path):
    store = Store(tmp_path / "db")
    owner = store.create_user("A")["id"]
    personal = Personalizer(store)
    for n in range(2):
        item = store.put(
            owner,
            "event",
            {
                "title": "Robotics Workshop",
                "importance": "medium",
                "participation": "unknown",
            },
            str(n),
        )
        personal.feedback(owner, item["id"], "importance", "high")
    assert (
        personal.apply(owner, {"title": "Robotics Workshop", "importance": "medium"})[
            "importance"
        ]
        == "high"
    )
    assert (
        personal.apply(owner, {"title": "Painting Workshop", "importance": "medium"})[
            "importance"
        ]
        == "medium"
    )
