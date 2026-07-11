import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.agents.models import Agent, AgentRun
from apps.agents.orchestrator import DEFAULT_MAX_STEPS, run_agent_loop
from services.hermes_service import HermesService

User = get_user_model()

DEFAULT_AGENT_SLUG = "general-operator"


def _get_or_create_default_agent():
    agent, _ = Agent.objects.get_or_create(
        slug=DEFAULT_AGENT_SLUG,
        defaults={
            "name": "General Operator",
            "skill": "agent-engineering/general-operator",
            "system_prompt": "Operate like a careful general-purpose engineering agent.",
            "default_max_steps": DEFAULT_MAX_STEPS,
            "allowed_tools": [],
        },
    )
    return agent


def _get_user(username):
    if username:
        return User.objects.get(username=username)

    user = User.objects.order_by("id").first()
    if not user:
        raise CommandError("No user exists in the database. Create a user before running the agent command.")
    return user


class Command(BaseCommand):
    help = "Execute a Hermes-backed agent run from the command line."

    def add_arguments(self, parser):
        parser.add_argument("-t", "--task", required=True, help="Mission text for the agent run")
        parser.add_argument("--agent", default=DEFAULT_AGENT_SLUG, help="Agent template slug")
        parser.add_argument("--user", default="", help="Username to run as. Defaults to the first user in the database.")
        parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="Maximum number of orchestration steps")

    def handle(self, *args, **options):
        task = options["task"]
        user = _get_user(options["user"])
        agent = _get_or_create_default_agent() if options["agent"] == DEFAULT_AGENT_SLUG else Agent.objects.filter(slug=options["agent"]).first()
        if agent is None:
            raise CommandError(f"Unknown agent slug: {options['agent']}")

        health = HermesService().health_check()
        if not health.get("connected"):
            raise CommandError(health.get("error") or "Hermes Gateway is unavailable.")

        run = AgentRun.objects.create(
            user=user,
            agent=agent,
            task=task,
            status="pending",
            max_steps=options["max_steps"],
            session_id=f"u{user.id}-run-cli",
        )

        hermes = HermesService(session_id=run.session_id)
        self.stdout.write(self.style.MIGRATE_HEADING(f"Run #{run.id} | agent={agent.slug}"))

        for event in run_agent_loop(run, hermes, max_steps=options["max_steps"], verbose=True):
            self._print_event(event)

        run.refresh_from_db()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Final status: {run.status}"))
        if run.answer:
            self.stdout.write("--- Final answer ---")
            self.stdout.write(run.answer)
        if run.error:
            self.stdout.write(self.style.ERROR(run.error))

    def _print_event(self, event):
        event_type = event.get("type")
        order = event.get("order")
        if event_type == "plan":
            self.stdout.write(f"[{order}] plan | {event.get('thought', '')}")
        elif event_type == "tool_call":
            self.stdout.write(f"[{order}] tool_call | {event.get('tool_name')} {json.dumps(event.get('tool_args', {}), ensure_ascii=False)}")
        elif event_type == "tool_result":
            result = event.get("tool_result", {})
            self.stdout.write(f"[{order}] tool_result | {event.get('tool_name')} ok={result.get('ok')}")
        elif event_type == "answer":
            self.stdout.write(f"[{order}] answer")
        elif event_type == "error":
            self.stdout.write(self.style.ERROR(f"[{order}] error | {event.get('content', {}).get('message', '')}"))
