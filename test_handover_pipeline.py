import os
import json
from data.groups import create_group, get_group, get_messages, delete_group
from data.handovers import (
    create_handover, get_handover, list_handovers_for_group,
    list_pending_handovers_for_user, approve_handover,
    set_group_handover_mode, get_group_handover_mode
)

def test_handover_pipeline():
    # 1. Create a test group
    grp = create_group(
        name="Dubai Handover Squad",
        created_by="agent_prakhar",
        members=["agent_deepak", "agent_rahul"],
        include_buddy=True,
    )
    group_id = grp["id"]
    print(f"[TEST 1] Group created: {group_id}")

    # 2. Test mode switching
    set_group_handover_mode(group_id, "external")
    assert get_group_handover_mode(group_id) == "external"
    set_group_handover_mode(group_id, "internal")
    assert get_group_handover_mode(group_id) == "internal"
    print("[TEST 2] Group handover mode switching verified")

    # 3. Test Internal Handover creation
    h_int = create_handover(
        group_id=group_id,
        group_name="Dubai Handover Squad",
        requester_id="agent_prakhar",
        requester_name="Prakhar",
        assigned_to="agent_deepak",
        mode="internal",
        requirement="Special trekking coverage in Alps for 12 people with extreme sports rider.",
    )
    assert h_int["status"] == "assigned"
    assert h_int["mode"] == "internal"
    print(f"[TEST 3] Internal handover created: {h_int['id']}")

    # 4. Test External Handover creation
    h_ext = create_handover(
        group_id=group_id,
        group_name="Dubai Handover Squad",
        requester_id="agent_prakhar",
        requester_name="Prakhar",
        assigned_to="agent_deepak",
        mode="external",
        requirement="Manager approval for 25% custom discount on Schengen Multi-trip.",
    )
    assert h_ext["status"] == "pending"
    assert h_ext["mode"] == "external"
    print(f"[TEST 4] External handover created: {h_ext['id']}")

    # 5. Check pending handovers for Deepak
    pending = list_pending_handovers_for_user("agent_deepak")
    assert len(pending) >= 1
    assert any(p["id"] == h_ext["id"] for p in pending)
    print(f"[TEST 5] Pending handovers list for agent_deepak verified ({len(pending)} found)")

    # 6. Test approval & auto-posting to group_messages
    res_data = {
        "plan_name": "Schengen Elite Custom Guard",
        "insurer": "Care Insurance Special Underwriting",
        "premium": "₹4,250",
        "sum_insured": "€100,000",
        "destination": "Europe / Schengen",
        "travel_dates": "15 May - 30 Jun 2026",
        "riders": "Adventure Sports + Zero Deductible",
        "notes": "Approved with 20% group volume discount.",
    }
    approved = approve_handover(h_ext["id"], "agent_deepak", res_data)
    assert approved["status"] == "approved"
    assert approved["resolution_data"]["premium"] == "₹4,250"

    # Check that message was posted to group_messages
    msgs = get_messages(group_id)
    assert len(msgs) >= 1
    assert "Schengen Elite Custom Guard" in msgs[0]["content"]
    assert "Care Insurance Special Underwriting" in msgs[0]["content"]
    print("[TEST 6] Handover approved and custom policy auto-posted to group chat!")

    # 7. Clean up
    delete_group(group_id)
    print("[TEST 7] Cleaned up test group")
    print("ALL HANDOVER BACKEND TESTS PASSED!")

if __name__ == "__main__":
    test_handover_pipeline()
