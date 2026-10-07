"""Process-wide offline guard for the authorized Phase 11 deterministic checks."""
import os
import socket
import sys
import importlib.machinery
import ipaddress
import ntpath
import shlex


_CLIENTS = {'ollama', 'curl', 'wget', 'openai', 'anthropic', 'llm', 'litellm',
            'claude', 'gemini', 'huggingface-cli'}


def _names_client(command):
    if command is None:
        return False
    if isinstance(command, (list, tuple)):
        return any(_names_client(arg) for arg in command)
    command = os.fsdecode(command)
    try:
        words = shlex.split(command, posix=False)
    except ValueError:
        words = [command]
    for word in words:
        name = ntpath.basename(word.strip('\"\'' )).lower()
        if name.endswith(('.exe', '.cmd', '.bat', '.com')):
            name = name.rsplit('.', 1)[0]
        if name in _CLIENTS or name in {'openai.cli', 'anthropic.cli'}:
            return True
    return False


def _process_command(event, args):
    # Audit signatures: Popen(executable, args, cwd, env);
    # exec/posix_spawn(path, argv, env); spawn(mode, path, argv, env).
    # Never stringify or inspect cwd/environment, including their keys.
    if event == 'subprocess.Popen' or event.startswith(('os.exec', 'os.posix_spawn')):
        return args[:2]
    if event.startswith('os.spawn'):
        return args[1:3] if args and isinstance(args[0], int) else args[:2]
    if event == 'os.system':
        return args[:1]
    return ()


def audit(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname',
                 'socket.gethostbyaddr', 'socket.sendto', 'socket.sendmsg'}:
        raise RuntimeError('PHASE11_OFFLINE_GUARD: network access blocked')
    if event == 'socket.bind' and isinstance(args[1], tuple):
        host = args[1][0]
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == 'localhost'
        if not loopback:
            raise RuntimeError('PHASE11_OFFLINE_GUARD: non-loopback bind blocked')
    if any(_names_client(command) for command in _process_command(event, args)):
        raise RuntimeError('PHASE11_OFFLINE_GUARD: external network/LLM client blocked')


def _blocked_client(*args, **kwargs):
    raise RuntimeError('PHASE11_OFFLINE_GUARD: LLM client entry point blocked')


_ENTRY_POINTS = {
    'src.summarization.summarize': ('call_ollama_json', 'prime_ollama_cache'),
    'pipeline.extract': ('call_ollama',),
    'experiments.document_evidence_pipeline.pipeline.extract': ('call_ollama',),
    'ollama': ('chat', 'generate', 'embed', 'embeddings', 'Client', 'AsyncClient'),
    'ollama._client': ('Client', 'AsyncClient'),
    'openai': ('OpenAI', 'AsyncOpenAI', 'AzureOpenAI', 'AsyncAzureOpenAI', 'Client', 'AsyncClient'),
    'openai._client': ('OpenAI', 'AsyncOpenAI', 'Client', 'AsyncClient'),
    'anthropic': ('Anthropic', 'AsyncAnthropic', 'Client', 'AsyncClient'),
    'anthropic._client': ('Anthropic', 'AsyncAnthropic', 'Client', 'AsyncClient'),
}


class _GuardLoader:
    def __init__(self, loader, names):
        self.loader, self.names = loader, names

    def create_module(self, spec):
        return self.loader.create_module(spec) if hasattr(self.loader, 'create_module') else None

    def exec_module(self, module):
        self.loader.exec_module(module)
        for name in self.names:
            if hasattr(module, name):
                setattr(module, name, _blocked_client)


class _GuardFinder:
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _ENTRY_POINTS:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and spec.loader is not None:
            spec.loader = _GuardLoader(spec.loader, _ENTRY_POINTS[fullname])
        return spec


sys.addaudithook(audit)
sys.meta_path.insert(0, _GuardFinder())
os.environ['PHASE11_GUARD_MODE'] = 'blocked'
try:
    socket.create_connection(('127.0.0.1', 11434), timeout=0.01)
except RuntimeError as exc:
    print(str(exc) + '; startup self-test PASS', flush=True)
else:
    os._exit(91)
os.environ['PHASE11_OFFLINE_GUARD_ACTIVE'] = '1'
