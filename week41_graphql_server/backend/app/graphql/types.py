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
    author = graphene.Field(lambda: UserType)
    project = graphene.Field(lambda: ProjectType)


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
