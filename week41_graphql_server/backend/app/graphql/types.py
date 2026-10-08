import graphene  # type: ignore

# ============================================================================
# Enums
# ============================================================================


class ProjectStatusEnum(graphene.Enum):
    """Lifecycle status of a project."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class TechCategoryEnum(graphene.Enum):
    """Categorization of a technology or skill."""

    FRONTEND = "FRONTEND"
    BACKEND = "BACKEND"
    DEVOPS = "DEVOPS"
    DATABASE = "DATABASE"
    MOBILE = "MOBILE"
    AI_ML = "AI_ML"


class UserRoleEnum(graphene.Enum):
    """System role and permission level for a developer profile."""

    DEVELOPER = "DEVELOPER"
    MAINTAINER = "MAINTAINER"
    ADMIN = "ADMIN"


# ============================================================================
# Interfaces
# ============================================================================


class TimestampedInterface(graphene.Interface):
    """Common interface for timestamped entities."""

    created_at = graphene.String(
        required=True, description="ISO-8601 creation timestamp."
    )
    updated_at = graphene.String(
        required=False, description="ISO-8601 update timestamp."
    )


def get_dataloaders(info):
    """Retrieves request-scoped dataloaders from execution context."""
    if not info:
        return None
    ctx = getattr(info, "context", None)
    if isinstance(ctx, dict):
        return ctx.get("dataloaders")
    if hasattr(ctx, "dataloaders"):
        return getattr(ctx, "dataloaders")
    return None


# ============================================================================
# Object Types
# ============================================================================


class TechnologyType(graphene.ObjectType):
    """Represents a programming language, framework, or tooling skill."""

    id = graphene.Int(required=True)
    name = graphene.String(required=True)
    category = graphene.Field(TechCategoryEnum, required=True)
    icon_slug = graphene.String()


class ReviewType(graphene.ObjectType):
    """Represents peer feedback and ratings on a project."""

    id = graphene.Int(required=True)
    rating = graphene.Int(required=True)
    comment = graphene.String()
    created_at = graphene.String(required=True)
    author_id = graphene.Int()
    project_id = graphene.Int()
    author = graphene.Field(lambda: UserType)
    project = graphene.Field(lambda: ProjectType)

    def resolve_author(self, info):
        if hasattr(self, "author") and self.author is not None:
            return self.author
        author_id = getattr(self, "author_id", None)
        if not author_id:
            return None

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "user_loader"):
            user = loaders.user_loader.load(author_id)
        else:
            from app.models.user_model import get_user_by_id

            user = get_user_by_id(author_id)
        return UserType(**user) if user else None

    def resolve_project(self, info):
        if hasattr(self, "project") and self.project is not None:
            return self.project
        project_id = getattr(self, "project_id", None)
        if not project_id:
            return None

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "project_loader"):
            proj = loaders.project_loader.load(project_id)
        else:
            from app.models.project_model import get_project_by_id

            proj = get_project_by_id(project_id)
        return ProjectType(**proj) if proj else None


class ProjectType(graphene.ObjectType):
    """Represents a showcase project created by a developer."""

    class Meta:
        interfaces = (TimestampedInterface,)

    id = graphene.Int(required=True)
    title = graphene.String(required=True)
    description = graphene.String()
    status = graphene.Field(ProjectStatusEnum, required=True)
    stars_count = graphene.Int(required=True)
    owner_id = graphene.Int(required=True)
    owner = graphene.Field(lambda: UserType)
    technologies = graphene.List(graphene.NonNull(TechnologyType))
    reviews = graphene.List(graphene.NonNull(ReviewType))
    average_rating = graphene.Float()
    review_count = graphene.Int()

    def resolve_owner(self, info):
        if hasattr(self, "owner") and self.owner is not None:
            return self.owner
        owner_id = getattr(self, "owner_id", None)
        if not owner_id:
            return None

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "user_loader"):
            user = loaders.user_loader.load(owner_id)
        else:
            from app.models.user_model import get_user_by_id

            user = get_user_by_id(owner_id)
        return UserType(**user) if user else None

    def resolve_technologies(self, info):
        if hasattr(self, "technologies") and self.technologies is not None:
            return self.technologies
        proj_id = getattr(self, "id", None)
        if not proj_id:
            return []

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "project_technologies_loader"):
            techs = loaders.project_technologies_loader.load(proj_id) or []
        else:
            from app.models.project_model import get_technologies_by_project

            techs = get_technologies_by_project(proj_id)
        return [TechnologyType(**t) for t in techs]

    def resolve_reviews(self, info):
        if hasattr(self, "reviews") and self.reviews is not None:
            return self.reviews
        proj_id = getattr(self, "id", None)
        if not proj_id:
            return []

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "project_reviews_loader"):
            revs = loaders.project_reviews_loader.load(proj_id) or []
        else:
            from app.models.project_model import get_reviews_by_project

            revs = get_reviews_by_project(proj_id)
        return [ReviewType(**r) for r in revs]


class UserType(graphene.ObjectType):
    """Represents a registered developer profile."""

    class Meta:
        interfaces = (TimestampedInterface,)

    id = graphene.Int(required=True)
    username = graphene.String(required=True)
    email = graphene.String(required=True)
    role = graphene.Field(UserRoleEnum, required=True)
    bio = graphene.String()
    projects = graphene.List(graphene.NonNull(ProjectType))
    reviews = graphene.List(graphene.NonNull(ReviewType))
    project_count = graphene.Int()

    def resolve_projects(self, info):
        if hasattr(self, "projects") and self.projects is not None:
            return self.projects
        user_id = getattr(self, "id", None)
        if not user_id:
            return []

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "owner_projects_loader"):
            projs = loaders.owner_projects_loader.load(user_id) or []
        else:
            from app.models.project_model import list_projects

            projs = list_projects(owner_id=user_id)
        return [ProjectType(**p) for p in projs]

    def resolve_reviews(self, info):
        if hasattr(self, "reviews") and self.reviews is not None:
            return self.reviews
        user_id = getattr(self, "id", None)
        if not user_id:
            return []

        loaders = get_dataloaders(info)
        if loaders and hasattr(loaders, "author_reviews_loader"):
            revs = loaders.author_reviews_loader.load(user_id) or []
        else:
            from app.models.project_model import get_reviews_by_author

            revs = get_reviews_by_author(user_id)
        return [ReviewType(**r) for r in revs]

    def resolve_project_count(self, info):
        if hasattr(self, "project_count") and self.project_count is not None:
            return self.project_count
        user_id = getattr(self, "id", None)
        if not user_id:
            return 0
        from app.models.project_model import list_projects

        return len(list_projects(owner_id=user_id))


class SystemStatsType(graphene.ObjectType):
    """Aggregate platform analytics and counters."""

    total_users = graphene.Int(required=True)
    total_projects = graphene.Int(required=True)
    total_reviews = graphene.Int(required=True)
    total_technologies = graphene.Int(required=True)


# ============================================================================
# Input Types
# ============================================================================


class UserInput(graphene.InputObjectType):
    """Input payload for registering a new developer."""

    username = graphene.String(required=True)
    email = graphene.String(required=True)
    role = graphene.Field(UserRoleEnum)
    bio = graphene.String()


class UserUpdateInput(graphene.InputObjectType):
    """Input payload for updating an existing developer."""

    username = graphene.String()
    email = graphene.String()
    role = graphene.Field(UserRoleEnum)
    bio = graphene.String()


class ProjectInput(graphene.InputObjectType):
    """Input payload for publishing a new project."""

    title = graphene.String(required=True)
    description = graphene.String()
    status = graphene.Field(ProjectStatusEnum)
    owner_id = graphene.Int(required=True)
    technology_ids = graphene.List(graphene.Int)


class ProjectUpdateInput(graphene.InputObjectType):
    """Input payload for editing an existing project."""

    title = graphene.String()
    description = graphene.String()
    status = graphene.Field(ProjectStatusEnum)
    technology_ids = graphene.List(graphene.Int)


class ReviewInput(graphene.InputObjectType):
    """Input payload for posting peer review feedback."""

    project_id = graphene.Int(required=True)
    author_id = graphene.Int(required=True)
    rating = graphene.Int(required=True)
    comment = graphene.String()


class ProjectFilterInput(graphene.InputObjectType):
    """Multi-parameter filter criteria for querying projects."""

    status = graphene.Field(ProjectStatusEnum)
    search = graphene.String()
    owner_id = graphene.Int()
    technology_id = graphene.Int()
    min_rating = graphene.Float()
