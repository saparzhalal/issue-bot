from database import (
    create_ticket,
    get_ticket,
    assign_ticket,
    update_ticket_status,
    get_ticket_history,
    get_tickets_by_status,
)


def new_ticket(category, item, location, photo, name, user_id, description):
    return create_ticket(
        category=category,
        item_name=item,
        location=location,
        photo_file_id=photo,
        requester_name=name,
        requester_id=user_id,
        issue_description=description,
    )


def fetch_ticket(ticket_id):
    return get_ticket(ticket_id)


def set_status(ticket_id, status, user, note=None):
    return update_ticket_status(ticket_id, status, user, note)


def assign(ticket_id, technician_name):
    return assign_ticket(ticket_id, technician_name)


def history(ticket_id):
    return get_ticket_history(ticket_id)


def by_status(status):
    return get_tickets_by_status(status)