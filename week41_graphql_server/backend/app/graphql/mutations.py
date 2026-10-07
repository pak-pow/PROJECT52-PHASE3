import graphene

from app.graphql.types import (
    ProjectInput,
    ProjectType,
    ProjectUpdateInput,
    ReviewInput,
    ReviewType,
    UserInput,
    UserType,
    UserUpdateInput,
)
from app.models.project_model import (
    create_project,
    create_review,
    delete_project,
    star_project,
    update_project,
)
from app.models.user_model import (
    create_user,
    delete_user,
    update_user,
)


class CreateUser(graphene.Mutation):
    """Registers a new developer profile."""

    class Arguments:
        input = UserInput(required=True)

    user = graphene.Field(UserType)
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, input):
        try:
            role_val = input.role.value if input.role else "DEVELOPER"
            user_data = create_user(
                username=input.username,
                email=input.email,
                role=role_val,
                bio=input.bio,
            )
            return CreateUser(
                user=UserType(**user_data),
                success=True,
                message="User registered successfully.",
            )
        except ValueError as err:
            return CreateUser(user=None, success=False, message=str(err))


class UpdateUser(graphene.Mutation):
    """Updates an existing developer profile."""

    class Arguments:
        id = graphene.Int(required=True)
        input = UserUpdateInput(required=True)

    user = graphene.Field(UserType)
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, id, input):
        try:
            role_val = input.role.value if input.role else None
            user_data = update_user(
                user_id=id,
                username=input.username,
                email=input.email,
                role=role_val,
                bio=input.bio,
            )
            if not user_data:
                return UpdateUser(
                    user=None,
                    success=False,
                    message=f"User with id {id} not found.",
                )
            return UpdateUser(
                user=UserType(**user_data),
                success=True,
                message="User updated successfully.",
            )
        except ValueError as err:
            return UpdateUser(user=None, success=False, message=str(err))


class DeleteUser(graphene.Mutation):
    """Removes a developer profile and cascades related entities."""

    class Arguments:
        id = graphene.Int(required=True)

    deleted_id = graphene.Int()
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, id):
        deleted = delete_user(id)
        if not deleted:
            return DeleteUser(
                deleted_id=None,
                success=False,
                message=f"User with id {id} not found.",
            )
        return DeleteUser(
            deleted_id=id,
            success=True,
            message="User deleted successfully.",
        )


class CreateProject(graphene.Mutation):
    """Publishes a new showcase project."""

    class Arguments:
        input = ProjectInput(required=True)

    project = graphene.Field(ProjectType)
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, input):
        try:
            status_val = input.status.value if input.status else "ACTIVE"
            proj_data = create_project(
                title=input.title,
                description=input.description,
                status=status_val,
                owner_id=input.owner_id,
                technology_ids=input.technology_ids,
            )
            return CreateProject(
                project=ProjectType(**proj_data),
                success=True,
                message="Project published successfully.",
            )
        except ValueError as err:
            return CreateProject(project=None, success=False, message=str(err))


class UpdateProject(graphene.Mutation):
    """Updates details or status of an existing project."""

    class Arguments:
        id = graphene.Int(required=True)
        input = ProjectUpdateInput(required=True)

    project = graphene.Field(ProjectType)
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, id, input):
        try:
            status_val = input.status.value if input.status else None
            proj_data = update_project(
                project_id=id,
                title=input.title,
                description=input.description,
                status=status_val,
                technology_ids=input.technology_ids,
            )
            if not proj_data:
                return UpdateProject(
                    project=None,
                    success=False,
                    message=f"Project with id {id} not found.",
                )
            return UpdateProject(
                project=ProjectType(**proj_data),
                success=True,
                message="Project updated successfully.",
            )
        except ValueError as err:
            return UpdateProject(project=None, success=False, message=str(err))


class DeleteProject(graphene.Mutation):
    """Deletes a showcase project and cascades its reviews."""

    class Arguments:
        id = graphene.Int(required=True)

    deleted_id = graphene.Int()
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, id):
        deleted = delete_project(id)
        if not deleted:
            return DeleteProject(
                deleted_id=None,
                success=False,
                message=f"Project with id {id} not found.",
            )
        return DeleteProject(
            deleted_id=id,
            success=True,
            message="Project deleted successfully.",
        )


class StarProject(graphene.Mutation):
    """Increments the star counter for a project."""

    class Arguments:
        id = graphene.Int(required=True)

    project = graphene.Field(ProjectType)
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, id):
        proj_data = star_project(id)
        if not proj_data:
            return StarProject(
                project=None,
                success=False,
                message=f"Project with id {id} not found.",
            )
        return StarProject(
            project=ProjectType(**proj_data),
            success=True,
            message="Project starred successfully.",
        )


class CreateReview(graphene.Mutation):
    """Submits peer review feedback and rating on a project."""

    class Arguments:
        input = ReviewInput(required=True)

    review = graphene.Field(ReviewType)
    success = graphene.Boolean(required=True)
    message = graphene.String()

    def mutate(self, info, input):
        try:
            rev_data = create_review(
                project_id=input.project_id,
                author_id=input.author_id,
                rating=input.rating,
                comment=input.comment,
            )
            return CreateReview(
                review=ReviewType(**rev_data),
                success=True,
                message="Review submitted successfully.",
            )
        except ValueError as err:
            return CreateReview(review=None, success=False, message=str(err))


class Mutation(graphene.ObjectType):
    """Root mutation definition for PulseGraph GraphQL schema."""

    create_user = CreateUser.Field(description="Register a new developer profile.")
    update_user = UpdateUser.Field(description="Update existing developer details.")
    delete_user = DeleteUser.Field(
        description="Remove developer profile and related projects."
    )
    create_project = CreateProject.Field(description="Publish a new developer project.")
    update_project = UpdateProject.Field(
        description="Update project details or status."
    )
    delete_project = DeleteProject.Field(
        description="Remove project and related reviews."
    )
    star_project = StarProject.Field(description="Increment star count for a project.")
    create_review = CreateReview.Field(
        description="Post peer review feedback on a project."
    )
