from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Role, UserProfile, VolunteerInviteCreate
from app.services.demo_store import store


def main() -> None:
    ngo = next(iter(store.ngos.values()))
    ngo.verification_status = "verified"
    store.ngos[ngo.id] = ngo

    volunteer = store.invite_volunteer(
        VolunteerInviteCreate(
            ngo_id=ngo.id,
            name="Phase2 Volunteer",
            email="phase2.volunteer@foodbridge.dev",
            phone="+910000000111",
        )
    )
    assert volunteer.status == "invited"
    assert "token=" in volunteer.invite_link

    token = volunteer.invite_link.split("token=")[-1]
    invite = store.get_volunteer_invite(token)
    assert invite is not None and not invite.used and not invite.revoked

    registered = store.activate_volunteer_from_invite(
        token=token,
        uid="phase2_uid",
        email="phase2.volunteer@foodbridge.dev",
    )
    assert registered.status == "pending_approval"
    assert registered.registered_uid == "phase2_uid"

    resent = store.resend_volunteer_invite(registered.id, ngo.id)
    assert "token=" in resent.invite_link

    store.users["phase2_uid"] = UserProfile(
        id="phase2_uid",
        role=Role.ngo_volunteer,
        display_name=registered.name,
        status="pending",
        entity_id=registered.ngo_id,
        email="phase2.volunteer@foodbridge.dev",
    )

    approved = store.set_volunteer_approval(registered.id, ngo.id, approved=True)
    assert approved.status == "active"

    print("[ok] Phase 2 volunteer flow checks passed")


if __name__ == "__main__":
    main()
