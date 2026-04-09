import traceback

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from ng_rdm.components import Col
from ng_rdm.utils import logger
from nicegui import Client, ui
from nicegui.page import page

from services.settings import config


def _is_api_request(request: Request) -> bool:
    """Check if request is for an API endpoint."""
    return "/api/" in request.url.path


def build_error_page(
    request: Request,
    status_code: int,
    title: str,
    message: str,
    show_traceback: bool = False,
    traceback_text: str = ""
) -> Response:
    """Build a consistent error page with app styling

    Args:
        request: FastAPI request object
        status_code: HTTP status code (403, 404, 500, etc.)
        title: Error title to display
        message: Error message to display
        show_traceback: Whether to show technical stack trace
        traceback_text: Stack trace text (if show_traceback is True)
    """
    # Choose icon and color based on status code
    if status_code == 403:
        icon = 'block'
        icon_color = 'orange-600'
    elif status_code == 404:
        icon = 'search_off'
        icon_color = 'blue-600'
    else:  # 500 and others
        icon = 'error_outline'
        icon_color = 'red-600'

    with Client(page(''), request=request) as client:
        with Col(classes='w-full min-h-screen bg-gray-50'):
            with Col(classes='mx-auto p-8'):
                with ui.card().classes('p-8').style('width: 800px; max-width: 95vw'):
                    with Col(classes='gap-4'):
                        ui.icon(icon, size='3em').classes(f'text-{icon_color}')
                        ui.label(title).classes('text-2xl font-semibold text-gray-800')
                        ui.separator()

                        if show_traceback and traceback_text:
                            # Development mode: show technical details
                            ui.markdown(f"**{message}**").classes('text-gray-700')
                            with ui.expansion('Stack trace', icon='code').classes('w-full'):
                                ui.markdown(f"```\n{traceback_text}\n```").classes('text-sm')
                        else:
                            # Production mode or user-friendly errors
                            ui.label(message).classes('text-gray-700')

                        ui.button('Terug naar home', on_click=lambda: ui.navigate.to('/')).props('flat color=primary')

    return client.build_response(request, status_code)


async def exception_handler_403(request: Request, exception: Exception) -> Response:
    """Handle 403 Forbidden errors with JSON for API or user-friendly page for UI"""
    logger.warning(f"403 Forbidden: {exception}")

    if _is_api_request(request):
        return JSONResponse(status_code=403, content={
            "detail": {"error": {"code": "FORBIDDEN", "message": str(exception) or "Access denied"}}
        })

    title = "403 - Geen toegang"
    message = str(exception) or "U heeft geen toegang tot deze pagina."

    return build_error_page(request, 403, title, message)


async def exception_handler_404(request: Request, exception: Exception) -> Response:
    """Handle 404 Not Found errors with JSON for API or user-friendly page for UI"""
    logger.info(f"404 Not Found: {request.url}")

    if _is_api_request(request):
        # Return JSON for API requests
        detail = getattr(exception, 'detail', None)
        if isinstance(detail, dict):
            return JSONResponse(status_code=404, content={"detail": detail})
        return JSONResponse(status_code=404, content={
            "detail": {"error": {"code": "NOT_FOUND", "message": str(exception) or "Resource not found"}}
        })

    title = "404 - Pagina niet gevonden"
    message = str(exception) or "De opgevraagde pagina kon niet worden gevonden."

    return build_error_page(request, 404, title, message)


async def exception_handler_500(request: Request, exception: Exception) -> Response:
    """Handle 500 errors with JSON for API or user-friendly page for UI"""
    stack_trace = traceback.format_exc()
    logger.error(f"500 Error: {exception}\n{stack_trace}")

    if _is_api_request(request):
        # Return JSON for API requests
        return JSONResponse(status_code=500, content={
            "detail": {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
        })

    # Determine message and whether to show technical details
    if config.get('DTAP', 'dev') == 'prod':
        # Production: generic message, hide details, send email
        title = "500 - Serverfout"
        message = "Er is een technische fout opgetreden. Het incident is gemeld en wordt onderzocht."
        show_details = False

        # Send email notification to admins
        try:
            from services.smtp_mail import sendmail_sync
            from_addr = config.get('error_notification_from', 'edupersona@example.com')
            to_addrs = config.get('error_notification_to', ['admin@example.com'])
            subject = "eduPersona 500 Error"
            body = f"URL: {request.url}\n\nException: {exception}\n\nStack trace:\n{stack_trace}"

            result = sendmail_sync(from_addr, to_addrs, subject, body)
            logger.info(f"Error notification email sent: {result}")
        except Exception as mail_error:
            logger.error(f"Failed to send error notification email: {mail_error}")
    else:
        # Development/Test: show technical details
        title = "500 - Serverfout"
        message = str(exception)
        show_details = True

    return build_error_page(request, 500, title, message, show_details, stack_trace)


def register_exception_handlers(app) -> None:
    """Register all exception handlers with the FastAPI app"""
    app.add_exception_handler(403, exception_handler_403)
    app.add_exception_handler(404, exception_handler_404)
    app.add_exception_handler(500, exception_handler_500)
    logger.info("Exception handlers registered")
