from datetime import datetime

from app.db import get_db
from app.models.user_model import get_user_by_id

VALID_STATUSES = {"DRAFT", "ACTIVE", "COMPLETED", "ARCHIVED"}


def create_project(
    title, description="", status="ACTIVE", owner_id=1, technology_ids=None
):
    """Publishes a new project showcase in the database."""
    if not title or not title.strip():
        raise ValueError("Project title cannot be empty.")

    owner = get_user_by_id(owner_id)
    if not owner:
        raise ValueError(f"Project owner with id {owner_id} does not exist.")

    status = (status or "ACTIVE").upper()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed statuses: "
            f"{', '.join(sorted(VALID_STATUSES))}."
        )

    title = title.strip()
    description = (description or "").strip()
    now = datetime.utcnow().isoformat() + "Z"

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO projects (
            title, description, status, stars_count, owner_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, 0, ?, ?, ?)
        """,
        (title, description, status, owner_id, now, now),
    )
    project_id = cursor.lastrowid

    if technology_ids:
        for tech_id in technology_ids:
            db.execute(
                """
                INSERT OR IGNORE INTO project_technologies (
                    project_id, technology_id
                ) VALUES (?, ?)
                """,
                (project_id, tech_id),
            )

    db.commit()
    return get_project_by_id(project_id)


def get_project_by_id(project_id):
    """Retrieves a single project record by id with rating metrics."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT p.id, p.title, p.description, p.status, p.stars_count,
               p.owner_id, p.created_at, p.updated_at,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS rev_count
        FROM projects p
        LEFT JOIN reviews r ON r.project_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        (project_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    data = dict(row)
    data["average_rating"] = (
        round(data["avg_rating"], 2) if data["rev_count"] > 0 else None
    )
    data["review_count"] = data["rev_count"]
    del data["avg_rating"]
    del data["rev_count"]
    return data


def list_projects(
    status=None,
    owner_id=None,
    technology_id=None,
    search=None,
    min_rating=None,
):
    """Retrieves projects matching the provided query filter criteria."""
    db = get_db()
    query = """
        SELECT p.id, p.title, p.description, p.status, p.stars_count,
               p.owner_id, p.created_at, p.updated_at,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS rev_count
        FROM projects p
        LEFT JOIN reviews r ON r.project_id = p.id
    """
    conditions = []
    params = []

    if technology_id is not None:
        query += """
            INNER JOIN project_technologies pt
            ON pt.project_id = p.id AND pt.technology_id = ?
        """
        params.append(technology_id)

    if status is not None:
        conditions.append("p.status = ?")
        params.append(status.upper())

    if owner_id is not None:
        conditions.append("p.owner_id = ?")
        params.append(owner_id)

    if search:
        conditions.append("(p.title LIKE ? OR p.description LIKE ?)")
        search_pattern = f"%{search.strip()}%"
        params.extend([search_pattern, search_pattern])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY p.id"

    if min_rating is not None:
        query += " HAVING avg_rating >= ?"
        params.append(float(min_rating))

    query += " ORDER BY p.id DESC"

    cursor = db.execute(query, params)
    projects = []
    for row in cursor.fetchall():
        item = dict(row)
        item["average_rating"] = (
            round(item["avg_rating"], 2) if item["rev_count"] > 0 else None
        )
        item["review_count"] = item["rev_count"]
        del item["avg_rating"]
        del item["rev_count"]
        projects.append(item)
    return projects


def update_project(
    project_id, title=None, description=None, status=None, technology_ids=None
):
    """Updates fields on an existing project."""
    project = get_project_by_id(project_id)
    if not project:
        return None

    db = get_db()
    new_title = title.strip() if title is not None else project["title"]
    new_desc = (
        description.strip() if description is not None else project["description"]
    )
    new_status = status.upper() if status is not None else project["status"]

    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'.")

    now = datetime.utcnow().isoformat() + "Z"
    db.execute(
        """
        UPDATE projects
        SET title = ?, description = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_title, new_desc, new_status, now, project_id),
    )

    if technology_ids is not None:
        db.execute(
            "DELETE FROM project_technologies WHERE project_id = ?",
            (project_id,),
        )
        for tech_id in technology_ids:
            db.execute(
                """
                INSERT OR IGNORE INTO project_technologies (
                    project_id, technology_id
                ) VALUES (?, ?)
                """,
                (project_id, tech_id),
            )

    db.commit()
    return get_project_by_id(project_id)


def delete_project(project_id):
    """Deletes a project record and cascades associated reviews."""
    project = get_project_by_id(project_id)
    if not project:
        return False

    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return True


def star_project(project_id):
    """Increments the stars count for a project."""
    project = get_project_by_id(project_id)
    if not project:
        return None

    db = get_db()
    db.execute(
        "UPDATE projects SET stars_count = stars_count + 1 WHERE id = ?",
        (project_id,),
    )
    db.commit()
    return get_project_by_id(project_id)


def create_review(project_id, author_id, rating, comment=""):
    """Creates a peer review rating and comment for a project."""
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError(f"Project with id {project_id} does not exist.")

    author = get_user_by_id(author_id)
    if not author:
        raise ValueError(f"Author with id {author_id} does not exist.")

    try:
        rating_val = int(rating)
    except (TypeError, ValueError):
        raise ValueError("Rating must be an integer between 1 and 5.")

    if rating_val < 1 or rating_val > 5:
        raise ValueError("Rating must be between 1 and 5.")

    comment_clean = (comment or "").strip()
    now = datetime.utcnow().isoformat() + "Z"

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO reviews (project_id, author_id, rating, comment, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, author_id, rating_val, comment_clean, now),
    )
    db.commit()

    rev_id = cursor.lastrowid
    return {
        "id": rev_id,
        "project_id": project_id,
        "author_id": author_id,
        "rating": rating_val,
        "comment": comment_clean,
        "created_at": now,
    }


def get_reviews_by_project(project_id):
    """Retrieves all reviews associated with a specific project."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, project_id, author_id, rating, comment, created_at
        FROM reviews
        WHERE project_id = ?
        ORDER BY id DESC
        """,
        (project_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_reviews_by_author(author_id):
    """Retrieves all reviews written by a specific author."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, project_id, author_id, rating, comment, created_at
        FROM reviews
        WHERE author_id = ?
        ORDER BY id DESC
        """,
        (author_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_technologies_by_project(project_id):
    """Retrieves all technologies tagged on a specific project."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT t.id, t.name, t.category, t.icon_slug
        FROM technologies t
        INNER JOIN project_technologies pt ON pt.technology_id = t.id
        WHERE pt.project_id = ?
        ORDER BY t.name ASC
        """,
        (project_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def list_technologies(category=None):
    """Retrieves technologies optionally filtered by domain category."""
    db = get_db()
    if category:
        cursor = db.execute(
            """
            SELECT id, name, category, icon_slug
            FROM technologies
            WHERE category = ?
            ORDER BY name ASC
            """,
            (category.upper(),),
        )
    else:
        cursor = db.execute("""
            SELECT id, name, category, icon_slug
            FROM technologies
            ORDER BY name ASC
            """)
    return [dict(row) for row in cursor.fetchall()]


def get_technology_by_id(tech_id):
    """Retrieves a single technology by primary key id."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, name, category, icon_slug
        FROM technologies
        WHERE id = ?
        """,
        (tech_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_system_stats():
    """Computes aggregate counts across all platform tables."""
    db = get_db()
    users_count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    projs_count = db.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
    revs_count = db.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"]
    techs_count = db.execute("SELECT COUNT(*) AS c FROM technologies").fetchone()["c"]
    return {
        "total_users": users_count,
        "total_projects": projs_count,
        "total_reviews": revs_count,
        "total_technologies": techs_count,
    }
