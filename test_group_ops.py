import sqlite3
import os
from data.groups import (
    create_group, get_group, list_groups_for_user, post_message,
    get_messages, add_member, remove_member, mark_read, get_all_unread_for_user,
    delete_group, BUDDY_USER_ID, BUDDY_DISPLAY_NAME
)

def test_groups_pipeline():
    # 1. Create group
    grp = create_group(
        name="Test Schengen Squad",
        created_by="agent_deepak",
        members=["agent_prakhar", "agent_rahul"],
        include_buddy=True,
    )
    assert grp is not None
    group_id = grp["id"]
    print(f"[TEST 1] Group created: {group_id}, has_buddy: {grp['has_buddy']}")
    assert grp["has_buddy"] is True
    assert len(grp["members"]) == 4  # deepak + prakhar + rahul + dolphin_buddy

    # 2. Prevent second bot in same group
    added_second = add_member(group_id, "dolphin_buddy", "agent_deepak", is_bot=1)
    assert added_second is False, "Should reject second Dolphin Buddy"
    print("[TEST 2] Enforced max 1 Dolphin Buddy per group")

    # 3. Post human message
    msg1 = post_message(
        group_id=group_id,
        sender_id="agent_deepak",
        sender_name="Deepak",
        content="Hey team, what plans for Dubai?",
    )
    print(f"[TEST 3] Human message posted: {msg1['id']}")

    # 4. Post Dolphin Buddy message
    msg2 = post_message(
        group_id=group_id,
        sender_id=BUDDY_USER_ID,
        sender_name=BUDDY_DISPLAY_NAME,
        content="Here are the top travel insurance options for Dubai: Digit Travel Guard and Care Explore.",
        msg_type="bot_response",
    )
    print(f"[TEST 4] Dolphin Buddy message posted: {msg2['id']}")

    # 5. Fetch messages
    msgs = get_messages(group_id)
    assert len(msgs) == 2
    print(f"[TEST 5] Fetched {len(msgs)} messages successfully")

    # 6. Unread count check for prakhar
    unread = get_all_unread_for_user("agent_prakhar")
    print(f"[TEST 6] Unread for prakhar: {unread.get(group_id)}")
    assert unread.get(group_id) == 2

    # Mark read
    mark_read(group_id, "agent_prakhar")
    unread_after = get_all_unread_for_user("agent_prakhar")
    assert unread_after.get(group_id) == 0
    print("[TEST 7] Read tracking verified")

    # 7. Clean up
    delete_group(group_id)
    assert get_group(group_id) is None
    print("[TEST 8] Group deletion and cleanup verified")
    print("ALL GROUP BACKEND TESTS PASSED!")

if __name__ == "__main__":
    test_groups_pipeline()
