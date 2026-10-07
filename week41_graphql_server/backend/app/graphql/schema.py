import graphene
from graphql import print_schema

from app.graphql.mutations import Mutation
from app.graphql.queries import Query
from app.graphql.types import (
    ProjectType,
    ReviewType,
    SystemStatsType,
    TechnologyType,
    TimestampedInterface,
    UserType,
)

# Instantiate executable Graphene GraphQL schema
schema = graphene.Schema(
    query=Query,
    mutation=Mutation,
    types=[
        TimestampedInterface,
        TechnologyType,
        ReviewType,
        ProjectType,
        UserType,
        SystemStatsType,
    ],
)


def get_sdl():
    """Generates the GraphQL Schema Definition Language (SDL) string."""
    return print_schema(schema.graphql_schema)


def execute_query(query_string, variables=None, context_value=None):
    """Executes a GraphQL query against the schema and returns the result."""
    return schema.execute(
        query_string,
        variables=variables,
        context_value=context_value,
    )
