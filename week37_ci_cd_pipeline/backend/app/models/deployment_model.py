from app.db import get_db_connection


class DeploymentModel:
    """Model for recording and querying deployment events across environments."""

    @staticmethod
    def create_deployment(
        service_name,
        environment,
        version,
        commit_hash,
        triggered_by="pipeline-runner",
        status="success",
        notes=None,
    ):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO deployments (
                service_name, environment, version, commit_hash,
                triggered_by, status, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_name,
                environment,
                version,
                commit_hash,
                triggered_by,
                status,
                notes,
            ),
        )
        conn.commit()
        deployment_id = cursor.lastrowid
        cursor.execute(
            "SELECT * FROM deployments WHERE id = ?", (deployment_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_deployments(environment=None, limit=50):
        conn = get_db_connection()
        cursor = conn.cursor()
        if environment:
            cursor.execute(
                """
                SELECT * FROM deployments
                WHERE environment = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (environment, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM deployments
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_latest_deployment(environment="production"):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM deployments
            WHERE environment = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (environment,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None


class PipelineRunModel:
    """Model for recording pipeline execution history and stage status."""

    @staticmethod
    def record_run(
        workflow_name,
        branch,
        commit_sha,
        lint_status,
        security_status,
        test_status,
        build_status,
        deploy_status,
        overall_status,
        duration_seconds=0.0,
    ):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pipeline_runs (
                workflow_name, branch, commit_sha,
                lint_status, security_status, test_status,
                build_status, deploy_status, overall_status,
                duration_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_name,
                branch,
                commit_sha,
                lint_status,
                security_status,
                test_status,
                build_status,
                deploy_status,
                overall_status,
                duration_seconds,
            ),
        )
        conn.commit()
        run_id = cursor.lastrowid
        cursor.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_recent_runs(limit=25):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM pipeline_runs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
