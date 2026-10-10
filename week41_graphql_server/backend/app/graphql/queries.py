import graphene  # type: ignore

from app.graphql.types import (
    ProjectFilterInput,
    ProjectStatusEnum,
    ProjectType,
    SystemStatsType,
    TechCategoryEnum,
    TechnologyType,
    UserRoleEnum,
    UserType,
)

# Baseline in-memory fixtures for Day 2 schema verification
MOCK_TECHNOLOGIES = [
    {
        "id": 1,
        "name": "Python",
        "category": TechCategoryEnum.BACKEND,
        "icon_slug": "python",
    },
    {
        "id": 2,
        "name": "GraphQL",
        "category": TechCategoryEnum.BACKEND,
        "icon_slug": "graphql",
    },
    {
        "id": 3,
        "name": "React",
        "category": TechCategoryEnum.FRONTEND,
        "icon_slug": "react",
    },
    {
        "id": 4,
        "name": "Docker",
        "category": TechCategoryEnum.DEVOPS,
        "icon_slug": "docker",
    },
]

MOCK_USERS = [
    {
        "id": 1,
        "username": "alex_dev",
        "email": "alex@pulsegraph.io",
        "role": UserRoleEnum.ADMIN,
        "bio": "Full-stack engineer building GraphQL APIs.",
        "created_at": "2026-10-01T08:00:00Z",
        "updated_at": "2026-10-05T12:00:00Z",
    },
    {
        "id": 2,
        "username": "sarah_cloud",
        "email": "sarah@pulsegraph.io",
        "role": UserRoleEnum.DEVELOPER,
        "bio": "Cloud and DevOps specialist.",
        "created_at": "2026-10-02T09:30:00Z",
        "updated_at": "2026-10-04T15:00:00Z",
    },
]

MOCK_PROJECTS = [
    {
        "id": 1,
        "title": "PulseGraph API",
        "description": "High-performance GraphQL server for developer portfolios.",
        "status": ProjectStatusEnum.ACTIVE,
        "stars_count": 42,
        "owner_id": 1,
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-05T14:30:00Z",
        "average_rating": 4.8,
        "review_count": 6,
    }
]


class Query(graphene.ObjectType):
    """Root query definition for PulseGraph GraphQL schema."""

    hello = graphene.String(description="Simple greeting probe for API availability.")
    version = graphene.String(
        description="Current release version of PulseGraph GraphQL API."
    )
    stats = graphene.Field(
        SystemStatsType, description="Platform statistics and metrics."
    )
    technologies = graphene.List(
        graphene.NonNull(TechnologyType),
        category=graphene.Argument(TechCategoryEnum),
        description="List all available technologies with optional category filter.",
    )
    users = graphene.List(
        graphene.NonNull(UserType),
        description="Retrieve all registered developer profiles.",
    )
    user = graphene.Field(
        UserType,
        id=graphene.Int(required=True),
        description="Retrieve a single developer by unique identifier.",
    )
    projects = graphene.List(
        graphene.NonNull(ProjectType),
        filter=graphene.Argument(ProjectFilterInput),
        description="Retrieve project catalog with optional filter criteria.",
    )
    project = graphene.Field(
        ProjectType,
        id=graphene.Int(required=True),
        description="Retrieve a specific project by unique identifier.",
    )
    viewer = graphene.Field(
        UserType,
        description="Retrieve currently authenticated user profile.",
    )
    admin_users = graphene.List(
        graphene.NonNull(UserType),
        description="Admin-only query to audit all users with full access.",
    )

    def resolve_hello(self, info):
        return "Welcome to PulseGraph GraphQL API"

    def resolve_version(self, info):
        return "1.0.0"

    def resolve_stats(self, info):
        try:
            from app.models.project_model import get_system_stats

            stats = get_system_stats()
            if stats["total_users"] > 0 or stats["total_technologies"] > 0:
                return SystemStatsType(**stats)
        except Exception:
            pass
        return SystemStatsType(
            total_users=len(MOCK_USERS),
            total_projects=len(MOCK_PROJECTS),
            total_reviews=6,
            total_technologies=len(MOCK_TECHNOLOGIES),
        )

    def resolve_technologies(self, info, category=None):
        try:
            from app.models.project_model import list_technologies

            cat_str = category.value if category else None
            db_techs = list_technologies(category=cat_str)
            if db_techs:
                return [TechnologyType(**t) for t in db_techs]
        except Exception:
            pass
        if category:
            return [
                TechnologyType(**t)
                for t in MOCK_TECHNOLOGIES
                if t["category"] == category
            ]
        return [TechnologyType(**t) for t in MOCK_TECHNOLOGIES]

    def resolve_users(self, info):
        try:
            from app.models.user_model import list_users

            db_users = list_users()
            if db_users:
                return [UserType(**u) for u in db_users]
        except Exception:
            pass
        return [UserType(**u) for u in MOCK_USERS]

    def resolve_user(self, info, id):
        try:
            from app.models.user_model import get_user_by_id

            db_user = get_user_by_id(id)
            if db_user:
                return UserType(**db_user)
        except Exception:
            pass
        match = next((u for u in MOCK_USERS if u["id"] == id), None)
        return UserType(**match) if match else None

    def resolve_projects(self, info, filter=None):
        try:
            from app.models.project_model import list_projects

            status_val = filter.status.value if filter and filter.status else None
            owner_val = filter.owner_id if filter and filter.owner_id else None
            tech_val = filter.technology_id if filter and filter.technology_id else None
            search_val = filter.search if filter and filter.search else None
            min_r = filter.min_rating if filter and filter.min_rating else None
            db_projs = list_projects(
                status=status_val,
                owner_id=owner_val,
                technology_id=tech_val,
                search=search_val,
                min_rating=min_r,
            )
            if db_projs:
                return [ProjectType(**p) for p in db_projs]
        except Exception:
            pass
        results = MOCK_PROJECTS
        if filter and filter.status:
            results = [p for p in results if p["status"] == filter.status]
        return [ProjectType(**p) for p in results]

    def resolve_project(self, info, id):
        try:
            from app.models.project_model import get_project_by_id

            db_proj = get_project_by_id(id)
            if db_proj:
                return ProjectType(**db_proj)
        except Exception:
            pass
        match = next((p for p in MOCK_PROJECTS if p["id"] == id), None)
        return ProjectType(**match) if match else None

    def resolve_viewer(self, info):
        from app.graphql.auth import get_current_user

        current_user = get_current_user(info)
        if not current_user:
            return None
        user_id = current_user.get("id") or current_user.get("sub")
        try:
            from app.models.user_model import get_user_by_id

            db_user = get_user_by_id(user_id)
            if db_user:
                return UserType(**db_user)
        except Exception:
            pass
        return None

    def resolve_admin_users(self, info):
        from graphql import GraphQLError

        from app.graphql.auth import get_current_user

        current_user = get_current_user(info)
        if not current_user:
            raise GraphQLError("Authentication required to access admin audit.")
        role = (current_user.get("role") or "").upper()
        if role != "ADMIN":
            raise GraphQLError("Access denied: ADMIN role required.")

        from app.models.user_model import list_users

        return [UserType(**u) for u in list_users()]
