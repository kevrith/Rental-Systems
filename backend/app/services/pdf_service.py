"""HTML-to-PDF rendering with Jinja2 + WeasyPrint.

WeasyPrint is imported lazily inside `render_pdf` so the module stays importable
where its native libraries are absent (test collection, lightweight workers).
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


@lru_cache
def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["kes"] = format_kes
    env.filters["longdate"] = format_long_date
    return env


def format_kes(value: Any) -> str:
    """`12345.6` -> `12,345.60`. Amounts always print to two decimals."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def format_long_date(value: Any) -> str:
    """`date(2026, 9, 3)` -> `3 September 2026`."""
    if value is None:
        return "—"
    try:
        return f"{value.day} {value.strftime('%B %Y')}"
    except AttributeError:
        return str(value)


def render_html(template_name: str, context: dict[str, Any]) -> str:
    return _environment().get_template(template_name).render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    from weasyprint import HTML

    html = render_html(template_name, context)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()


def render_string_to_pdf(html: str) -> bytes:
    """Render an already-substituted HTML body — used by the lease template editor,
    where the body comes from the database rather than a file."""
    from weasyprint import HTML

    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()


@lru_cache
def _string_environment() -> SandboxedEnvironment:
    """Separate environment for landlord-authored template bodies.

    Sandboxed because `body` is untrusted template *source*, not just untrusted
    data — a landlord account (or one compromised via XSS/leaked creds) could
    otherwise use Jinja2 template syntax itself to reach arbitrary Python
    objects (e.g. `{{ ''.__class__.__mro__[1].__subclasses__() }}`) and achieve
    RCE. Autoescape is forced on here too: interpolated values — tenant names,
    addresses and other captured data — get escaped, so a tenant cannot inject
    markup into a lease by way of their own name.
    """
    env = SandboxedEnvironment(autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters["kes"] = format_kes
    env.filters["longdate"] = format_long_date
    return env


def substitute(body: str, variables: dict[str, Any]) -> str:
    """Fill `{{ placeholders }}` in a user-authored lease template."""
    return _string_environment().from_string(body).render(**variables)
