import sys
import json
import subprocess
import yaml

from collections import OrderedDict

import click
import kubernetes
from kubernetes.client.rest import ApiException
import requests
import re

DEFAULT_CONSUL_URL = 'http://localhost:8500'
DEFAULT_INTERVAL = '30s'
DEFAULT_CHECK_IP = '127.0.0.1'
DEFAULT_CONSUL_SINK_URL = '127.0.0.1:8500'
DEFAULT_CONSUL_SINK_DOMAIN = '.consul'
DEFAULT_CONSUL_SINK_PATH = '/v1/agent/service/register'
DEFAULT_SVC_FILE = '/etc/consul.d/consulk8s_services.json'
DEFAULT_BACKEND_PORT = 80

yaml.warnings({'YAMLLoadWarning': False})

@click.group()
@click.option('--k8s-config', '-k', default=None, metavar='PATH',
              help='Path to kubeconfig file (default: <kubectl behavior>)')
@click.option('--k8s-context', '-c', default=None, metavar='NAME',
              help='Kubeconfig context to use (default: <current-context>)')
def cli(k8s_config, k8s_context):
    kubernetes.config.load_kube_config(config_file=k8s_config,
                                       context=k8s_context)


@cli.command(name='write-ingresses')
@click.option('--service-file', '-s', default=DEFAULT_SVC_FILE, metavar='PATH',
              help='File to write (default: {})'.format(DEFAULT_SVC_FILE))
@click.option('--default-ip', '--check-ip',
              default=DEFAULT_CHECK_IP, metavar='IP',
              help='Default Ingress IP (default: {})'.format(DEFAULT_CHECK_IP))
@click.option('--consul-sink-url', '-c',
              default=None, metavar='STRING',
              help='Consul Sink url to upload services to (default: {})'.format(DEFAULT_CONSUL_SINK_URL))
@click.option('--consul-sink-domain', '-d',
              default=DEFAULT_CONSUL_SINK_DOMAIN, metavar='STRING',
              help='Consul Sink domain, used to upload services to (default: {})'.format(DEFAULT_CONSUL_SINK_DOMAIN))
@click.option('--consul-sink-path', default=DEFAULT_CONSUL_SINK_PATH, metavar='PATH',
              help='Path on Consul Sink (default: {})'.format(DEFAULT_CONSUL_SINK_PATH))
@click.option('--host-as-name', '-h', default=False, is_flag=True, metavar='BOOL', type=click.BOOL,
              help='Use the ingress host as service name to help dns query (default: False)')
@click.option('--verbose', '-v', default=False, is_flag=True, metavar='BOOL', type=click.BOOL,
              help='Show output (default: False)')
@click.option('--skip-checks', default=False, is_flag=True, metavar='BOOL', type=click.BOOL,
              help='Skip checks (default: False)')
@click.option('--check-interval', '-i', default='30s', metavar='INTERVAL',
              help='HTTP check interval (default: {})'.format(DEFAULT_INTERVAL))
@click.option('--code-when-changed', default=0, metavar='NUM', type=click.INT,
              help='Exit code to return when services file is changed')
@click.option('--change-command', '-C', default=None, metavar='CMD',
              help='Command to run if service file is changed')

def write_ingresses(service_file, default_ip, consul_sink_url, consul_sink_domain, consul_sink_path, host_as_name, verbose, skip_checks, check_interval, code_when_changed,
                    change_command):
    services =  []
    ingresses = get_k8s_ingresses()
    services += k8s_ingresses_as_services(ingresses, default_ip=default_ip, interval=check_interval, host_as_name=host_as_name, consul_sink_domain=consul_sink_domain)
    
    ingress_routes = get_k8s_ingress_routes()
    services += k8s_ingresses_as_services(ingress_routes, default_ip=default_ip, interval=check_interval, host_as_name=host_as_name, consul_sink_domain=consul_sink_domain)
    
    
    if consul_sink_url:
        try:
            return_status_code = put_services(services, consul_sink_url=consul_sink_url, consul_sink_domain=consul_sink_domain, consul_sink_path=consul_sink_path, code_when_changed=code_when_changed, change_command=change_command, verbose=verbose, skip_checks=skip_checks)
            if return_status_code != 200:
                click.echo('HTTP Error {}'.format(return_status_code))
        except Exception as error:
            click.echo('An exception occurred: {}'.format(error))
            pass

    else:
        try:
            click.echo('Reading {}'.format(service_file))
            with open(service_file, 'r') as f:
                current_json = f.read()
        except FileNotFoundError:
            current_json = None
        if skip_checks:
            for service in services:
                del service['checks']
        data = {'services': services}
        json_to_write = json.dumps(data, indent=2) + '\n'
        if verbose:
            click.echo(json_to_write)
        if json_to_write != current_json:
            click.echo('Writing {}...'.format(service_file))
            with open(service_file, 'w') as f:
                f.write(json_to_write)
            click.echo('Done!')
            exec_change_command(change_command=change_command, code_when_changed=code_when_changed)
        else:
            click.echo('No changes')
            sys.exit(0)

def get_k8s_ingresses():
    k8s = kubernetes.client.ExtensionsV1beta1Api()
    return k8s.list_ingress_for_all_namespaces().items

def get_k8s_ingress_routes():
    crd_name = 'ingressroutes.traefik.containo.us'
    crd_group = 'traefik.containo.us'
    crd_version = 'v1alpha1'
    crd_plural = 'ingressroutes'
    ingress_routes = []
    try:
        custom_api_instance = kubernetes.client.CustomObjectsApi()
        api_response = custom_api_instance.list_cluster_custom_object(group=crd_group, version=crd_version, plural=crd_plural)
        ingress_routes = api_response['items']
    except ApiException:
        print("No resource %s found\n" % crd_name)
    return ingress_routes


def k8s_ingresses_as_services(ingresses, default_ip, interval, host_as_name, consul_sink_domain):
    """
    Build a dict of Consul Service definitions based on k8s ingress resources.

    :param ingresses: Ingress resources to convert to service definitions.
    :type ingresses: list

    :param default_ip: IP against which to issue service checks if none is found
        in the Ingress loadBalancer status.
    :type default_ip: str

    :param interval: Consul check interval at which to run service checks.
    :type interval: str

    :return: List of Consul services
    :rtype: list
    """
    services = []
    for ingress in ingresses:
        useObject = False
        if type(ingress) is dict:
            useObject = True
        if useObject:
            ingress_name = '{}/{}'.format(ingress['metadata']['namespace'], ingress['metadata']['name'])
            ann = ingress['metadata']['annotations']
        else:
            ingress_name = '{}/{}'.format(ingress.metadata.namespace, ingress.metadata.name) 
            ann = ingress.metadata.annotations
        name = ann.get('consulk8s/service') if ann is not None else None
        if host_as_name:
            try:
                def rreplace(s, old, new, occurrence=1):
                    li = s.rsplit(old, occurrence)
                    return new.join(li)
                if useObject:
                    pattern = "\(\`(.+\.*)\..*\`"
                    name = re.findall(pattern, ingress['spec']['routes'][0]['match'])[0]                 
                else:
                    name = rreplace(ingress.spec.rules[0].host, consul_sink_domain, '')
            except (KeyError, IndexError):
                click.echo('Ingress "{}" has no host!'.format(ingress_name),
                           err=True)
                sys.exit(1)
        if name is None or not name:
            if ingress_name:
                name = ingress_name
            else:
                continue
        ip = ann.get('consulk8s/address')
        if ip is None:
            if not useObject and ingress.status.load_balancer.ingress:
                status = ingress.status.load_balancer.ingress[0]
                ip = status.ip or default_ip
            else:
                ip = default_ip

        port_ = ann.get('consulk8s/port')
        if port_ == None:
            if useObject:
                port_ = DEFAULT_BACKEND_PORT
            else:
                port_ = ingress.spec.rules[0].http.paths[0].backend.service_port if hasattr(ingress.spec.rules[0], "http") and type(ingress.spec.rules[0].http.paths[0].backend.service_port) == type(int(1)) else DEFAULT_BACKEND_PORT
        try:
            port = int(port_)
        except ValueError:
            click.echo('Ingress "{}" bad port: {}'.format(ingress_name, port_),
                       err=True)
            sys.exit(1)

        check_host = ann.get('consulk8s/check_host')
        if check_host is None:
            try:
                if useObject:
                    pattern = "\(\`(.+).*\`\) "
                    check_host = re.findall(pattern, ingress['spec']['routes'][0]['match'])[0]                 
                else:
                    check_host = ingress.spec.rules[0].host
            except (KeyError, IndexError):
                click.echo('Ingress "{}" has no host!'.format(ingress_name),
                           err=True)
                sys.exit(1)

        check_timeout = ann.get('consulk8s/check_timeout', '2s')
        check_path = ann.get('consulk8s/check_path', '/').lstrip('/')
        check_scheme = 'https' if port == 443 else 'http'

        check = OrderedDict((
            ('name', '{} check'.format(name)),
            ('notes', 'HTTP check {} on port {} every {}'.format(
                check_host, port, interval)),
            ('http', '{}://{}:{}/{}'.format(check_scheme, ip, port,
                                            check_path)),
            ('interval', interval),
            ('header', {'Host': [check_host]}),
            ('timeout', check_timeout)
        ))

        if ann.get('consulk8s/tls_skip_verify', 'false') == 'true':
            check['tls_skip_verify'] = True

        services.append(OrderedDict((
            ('id', 'consulk8s_{}'.format(name)),
            ('name', name),
            ('address', ip),
            ('port', port),
            ('checks', [check])
         )))
    return services

def exec_change_command(change_command, code_when_changed):
    if change_command is not None:
        click.echo('Running: {}...'.format(change_command))
        result = subprocess.run(change_command, shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        click.echo(result.stdout, nl=False)
        click.echo(result.stderr, err=True, nl=False)
    sys.exit(code_when_changed)

def put_services(services, consul_sink_url, consul_sink_domain, consul_sink_path, code_when_changed, change_command, verbose, skip_checks):
    click.echo('Putting to {}...'.format(consul_sink_url+consul_sink_path))
    port = consul_sink_url.rsplit(':',1)
    put_scheme = 'https://' if port == 443 else 'http://'
    
    for service in services:
        del service['id']
        if skip_checks:
            del service['checks']
        if service['Tags'] if 'Tags' in service else False:
            service['Tags'].extend(['k8s', 'k8s-ingress'])
        else:
            service['Tags'] = ['k8s', 'k8s-ingress']
        json_to_put = json.dumps(service, indent=4) + '\n'  
        if verbose:
            click.echo(json_to_put)
        response = requests.put(put_scheme+consul_sink_url+consul_sink_path, data =json_to_put) 
        if response.status_code != 200:
            break    
    click.echo('Completed Put')

    exec_change_command(change_command=change_command, code_when_changed=code_when_changed)
    return response.status_code


if __name__ == '__main__':
    cli()
