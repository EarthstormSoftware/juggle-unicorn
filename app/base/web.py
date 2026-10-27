"""
The web page and JSON API, on port 80, with Microdot.

Every product has: GET / (its page, www/index.html), the base's shared style and script (/base.css, /base.js),
GET /api/info, GET and POST /api/config, POST /api/restart and POST /api/reset. A light also has POST
/api/power/on, /api/power/off, /api/power/toggle, /api/mode ({"mode", "parameters"}) and /api/brightness
({"brightness"}), as PlasmaStick's. The product can add its own (routes(app, device)).

Two guards before every request: a POST that a browser sends from another site's page is refused (so a malicious page
can't use the device through the browser), and with a web password set, every request needs it (HTTP Basic auth,
any username). It's sent unencrypted, so it keeps out other people on the network rather than a determined attacker.
"""
from base.compat import asyncio, a2b_base64, beside
from base.log import Log
from base.microdot import Microdot, Response
from base.passwords import check_password

TAG = 'HTTP'
BASE_WWW = beside(__file__, 'www')
TEXT = {'Content-Type': 'text/plain; charset=utf-8'}


def origin_allowed(headers):
    """False for a POST a browser sent from another site's page. Browsers send Origin on such requests; scripts like
    curl send none and are allowed."""
    origin = headers.get('Origin')
    if not origin:
        return True
    return origin.split('://', 1)[-1].rstrip('/') == headers.get('Host', '')


def password_ok(headers, password_hash):
    """True if HTTP Basic auth in headers carries the password hashed in password_hash (any username)."""
    auth = headers.get('Authorization', '')
    if not auth.startswith('Basic '):
        return False
    try:
        decoded = a2b_base64(auth[6:].strip()).decode('utf-8')
    except (ValueError, UnicodeError):
        return False
    return check_password(decoded.partition(':')[2], password_hash)


def _file(path, content_type):
    response = Response.send_file(path, content_type=content_type)
    response.headers['Cache-Control'] = 'no-store'
    return response


def create(device):
    app = Microdot()
    accepted = {'auth': None}  # the last Authorization header that passed, so the hash isn't redone per request

    @app.before_request
    async def guard(request):
        if request.method == 'POST' and not origin_allowed(request.headers):
            Log.warn(TAG, 'Refused a cross-site POST to {} from {}'.format(request.path, request.headers.get('Origin')))
            return 'Cross-site request refused', 403, TEXT
        password_hash = device.settings.get('web', 'password')
        auth = request.headers.get('Authorization')
        if password_hash and not (auth and auth == accepted['auth']):
            if password_ok(request.headers, password_hash):
                accepted['auth'] = auth
            else:
                return 'Password required', 401, dict(TEXT, **{
                    'WWW-Authenticate': 'Basic realm="{}", charset="UTF-8"'.format(device.product.NAME)})

    @app.get('/')
    async def index(request):
        return _file(device.www + '/index.html', 'text/html; charset=utf-8')

    @app.get('/base.css')
    async def base_css(request):
        return _file(BASE_WWW + '/base.css', 'text/css; charset=utf-8')

    @app.get('/base.js')
    async def base_js(request):
        return _file(BASE_WWW + '/base.js', 'text/javascript; charset=utf-8')

    @app.get('/favicon.ico')
    async def favicon(request):
        return '', 204, {}

    @app.get('/api/info')
    async def info(request):
        return device.info()

    @app.get('/api/config')
    async def get_config(request):
        return device.settings.view()

    @app.post('/api/config')
    async def set_config(request):
        error, changed = device.settings.update(_json(request))
        if error:
            return {'success': False, 'error': error}, 400
        restart = device.settings.restart_needed(changed)
        device.applied(changed)
        if restart:
            asyncio.create_task(device.restart_soon())
        return {'success': True, 'restart_required': restart}

    @app.post('/api/restart')
    async def restart(request):
        asyncio.create_task(device.restart_soon())
        return {'success': True}

    @app.post('/api/reset')
    async def reset(request):
        # Needs confirm, so a stray request can't wipe the settings
        if _json(request).get('confirm') is not True:
            return {'success': False, 'error': 'confirm must be true'}, 400
        device.reset()
        asyncio.create_task(device.restart_soon())
        return {'success': True}

    if device.light is not None:
        light = device.light

        @app.post('/api/power/on')
        async def power_on(request):
            light.set(on=True)
            return {'success': True, 'state': 'on'}

        @app.post('/api/power/off')
        async def power_off(request):
            light.set(on=False)
            return {'success': True, 'state': 'off'}

        @app.post('/api/power/toggle')
        async def power_toggle(request):
            return {'success': True, 'state': 'on' if light.toggle() else 'off'}

        @app.post('/api/mode')
        async def mode(request):
            data = _json(request)
            error = light.set(mode=data.get('mode'), parameters=data.get('parameters'))
            if error:
                return {'success': False, 'error': error}, 400
            return {'success': True, 'mode': light.mode}

        @app.post('/api/brightness')
        async def brightness(request):
            error = light.set(brightness=_json(request).get('brightness'))
            if error:
                return {'success': False, 'error': error}, 400
            return {'success': True, 'brightness': light.brightness}

    if hasattr(device.product, 'routes'):
        device.product.routes(app, device)

    @app.errorhandler(404)
    async def not_found(request):
        return 'Not Found', 404, TEXT

    @app.errorhandler(500)
    async def internal_error(request):
        return 'Internal Server Error', 500, TEXT

    return app


def _json(request):
    try:
        data = request.json
    except ValueError:
        data = None
    return data if isinstance(data, dict) else {}
