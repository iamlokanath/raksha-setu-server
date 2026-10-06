from common.timeutil import isoformat


def vulnerability_of(report) -> dict:
    return {
        "children": report.children,
        "older_adults": report.older_adults,
        "pregnant_women": report.pregnant_women,
        "persons_with_disability": report.persons_with_disability,
        "injured_or_sick": report.injured_or_sick,
    }


def resources_of(report) -> list[dict]:
    return [
        {"resource_type": "food", "quantity": report.food_quantity, "unit": report.food_unit},
        {"resource_type": "water", "quantity": report.water_quantity, "unit": report.water_unit},
        {"resource_type": "medicine", "quantity": report.medicine_quantity, "unit": report.medicine_unit},
    ]


def report_out(report) -> dict:
    return {
        "id": str(report.id),
        "client_report_id": str(report.client_report_id),
        "shelter_id": str(report.shelter_id),
        "reported_at": isoformat(report.reported_at),
        "received_at": isoformat(report.received_at),
        "population": report.population,
        "vulnerability": vulnerability_of(report),
        "resources": resources_of(report),
        "incident_notes": report.incident_notes,
        "channel": report.channel,
        "applied_to_current": report.applied_to_current,
        "processing_status": "accepted",
    }


def shelter_out(shelter) -> dict:
    return {
        "id": str(shelter.id),
        "tenant_id": str(shelter.tenant_id),
        "block_id": str(shelter.block_id),
        "name": shelter.name,
        "location_label": shelter.location_label,
        "latitude": shelter.latitude,
        "longitude": shelter.longitude,
        "capacity": shelter.capacity,
        "warden_user_id": str(shelter.warden_user_id),
        "reporting_contact": shelter.reporting_contact,
        "operational_status": shelter.operational_status,
        "current_status": shelter.current_status,
        "current_population": shelter.current_population,
        "last_applied_report_at": isoformat(shelter.last_applied_report_at),
    }


def alert_out(alert) -> dict:
    return {
        "id": str(alert.id),
        "shelter_id": str(alert.shelter_id),
        "type": alert.type,
        "resource_type": alert.resource_type,
        "severity": alert.severity,
        "status": alert.status,
        "created_at": isoformat(alert.created_at),
    }


def action_out(action) -> dict:
    return {
        "id": str(action.id),
        "alert_id": str(action.alert_id),
        "source_shelter_id": str(action.source_shelter_id),
        "destination_shelter_id": str(action.destination_shelter_id),
        "resource_type": action.resource_type,
        "suggested_quantity": action.suggested_quantity,
        "approved_quantity": action.approved_quantity,
        "decision": action.decision,
        "status": action.status,
        "decision_note": action.decision_note,
        "decided_at": isoformat(action.decided_at),
        "receipt_confirmed_at": isoformat(action.receipt_confirmed_at),
        "explanation_key": action.explanation_key,
        "explanation_params": action.explanation_params,
    }


def user_out(user, assignment) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "organization": user.organization,
        "status": user.status,
        "shelter_id": str(assignment.shelter_id) if assignment and assignment.shelter_id else None,
        "block_id": str(assignment.block_id) if assignment and assignment.block_id else None,
        "support_functions": list(assignment.support_functions or []) if assignment else [],
        "grants": list(user.grants or []),
    }
