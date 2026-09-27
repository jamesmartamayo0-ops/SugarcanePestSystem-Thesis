import click
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import User, UserRole, normalize_username


def register_cli(app) -> None:
    @app.cli.command("create-admin")
    def create_admin() -> None:
        """Interactively bootstrap the first administrator."""
        try:
            if db.session.scalar(select(User.id).where(User.role == UserRole.ADMIN).limit(1)) is not None:
                raise click.ClickException("An administrator already exists; use the admin workflow.")
        except SQLAlchemyError:
            raise click.ClickException("Unable to verify administrator status.") from None
        finally:
            db.session.rollback()

        username_input = click.prompt("Username", type=str)
        try:
            username = normalize_username(username_input)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from None

        full_name = click.prompt("Full name", type=str).strip()
        if not full_name or len(full_name) > 160:
            raise click.ClickException("Full name must be 1-160 characters.")

        try:
            if db.session.scalar(select(User.id).where(User.username == username).limit(1)) is not None:
                raise click.ClickException("Username already exists.")
        except SQLAlchemyError:
            raise click.ClickException("Unable to verify username availability.") from None
        finally:
            db.session.rollback()

        password = click.prompt("Password", hide_input=True, confirmation_prompt=True, type=str)
        user = User(username=username, full_name=full_name, role=UserRole.ADMIN, is_active=True)
        try:
            user.set_password(password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from None

        try:
            # Serialize simultaneous bootstrap attempts without holding a lock during prompts.
            db.session.execute(text("SELECT pg_advisory_xact_lock(75240201)"))
            if db.session.scalar(select(User.id).where(User.role == UserRole.ADMIN).limit(1)) is not None:
                raise click.ClickException("An administrator already exists; use the admin workflow.")
            if db.session.scalar(select(User.id).where(User.username == username).limit(1)) is not None:
                raise click.ClickException("Username already exists.")
            db.session.add(user)
            db.session.commit()
        except click.ClickException:
            db.session.rollback()
            raise
        except IntegrityError:
            db.session.rollback()
            raise click.ClickException("Username already exists.") from None
        except SQLAlchemyError:
            db.session.rollback()
            raise click.ClickException("Unable to create administrator account.") from None

        click.echo("Administrator account created.")
