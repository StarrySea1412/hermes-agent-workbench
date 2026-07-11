"""Celery tasks for asynchronous chapter generation."""

import logging

from celery import shared_task
from django.utils import timezone

from apps.ai_config.models import AIConfig, GenerationTask

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="ai_config.generate_chapter",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=2,
)
def generate_chapter_task(self, task_id):
    try:
        gen_task = GenerationTask.objects.select_related('chapter', 'chapter__bid', 'user').get(id=task_id)
    except GenerationTask.DoesNotExist:
        logger.error("GenerationTask %s does not exist", task_id)
        return

    GenerationTask.objects.filter(id=task_id).update(
        status='running',
        celery_task_id=self.request.id,
        updated_at=timezone.now(),
    )

    chapter = gen_task.chapter
    chapter_title = chapter.title
    bid_id = chapter.bid_id
    user_id = gen_task.user_id

    try:
        if gen_task.mode == 'hermes':
            from apps.agents.skill_loader import build_system_prompt
            from services.hermes_service import build_session_id, create_hermes_service

            session_id = build_session_id(user_id, bid_id)
            hermes_service = create_hermes_service(session_id=session_id)
            if not hermes_service:
                raise RuntimeError("Hermes Agent Gateway 不可用")

            system_prompt = None
            if gen_task.skill:
                system_prompt = build_system_prompt(gen_task.skill)
                if not system_prompt:
                    raise RuntimeError(f"无法加载 Hermes skill: {gen_task.skill}")

            generated_text = hermes_service.generate_chapter(
                chapter_title=chapter_title,
                prompt=gen_task.prompt or None,
                context=gen_task.context or None,
                system_prompt=system_prompt,
            )
            canvas_content = hermes_service.to_canvas_format(generated_text)
        else:
            try:
                config = AIConfig.objects.get(user_id=user_id, is_active=True)
            except AIConfig.DoesNotExist:
                raise RuntimeError("请先配置 AI 设置")

            from services.ai_service import AIService

            ai_service = AIService(config)
            generated_text, canvas_content = ai_service.generate_chapter_content(
                chapter_title=chapter_title,
                prompt=gen_task.prompt or None,
                context=gen_task.context or None,
            )

        gen_task.refresh_from_db()
        gen_task.status = 'done'
        gen_task.result = {
            'content': canvas_content,
            'generated_text': generated_text,
            'mode': gen_task.mode,
            'skill': gen_task.skill or None,
        }
        gen_task.error = ''
        gen_task.completed_at = timezone.now()
        gen_task.save()
        logger.info("GenerationTask %s completed, output=%s chars", task_id, len(generated_text))

    except Exception as exc:
        retries_done = self.request.retries
        logger.warning("GenerationTask %s failed (%s/%s): %s", task_id, retries_done, self.max_retries, exc)

        if retries_done >= self.max_retries:
            gen_task.refresh_from_db()
            gen_task.status = 'failed'
            gen_task.error = str(exc)
            gen_task.completed_at = timezone.now()
            gen_task.save()
        raise
