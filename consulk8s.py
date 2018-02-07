import sys
import json

from collections import OrderedDict

import click
import kubernetes

DEFAULT_CONSUL_URL = 'http://localhost:8500'
DEFAULT_INTERVAL = '30s'
DEFAULT_CHECK_IP = '127.0.0.1'
DEFAULT_SVC_FILE = '/etc/consul.d/consulk8s_services.json'


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
@click.option('--check-ip', default=DEFAULT_CHECK_IP, metavar='IP',
              help='IP for HTTP checks (default: {})'.format(DEFAULT_CHECK_IP))
@click.option('--check-interval', '-i', default='30s', metavar='INTERVAL',
              help='HTTP check interval (default: {})'.format(DEFAULT_INTERVAL))
@click.pass_context
def write_ingresses(ctx, service_file, check_ip, check_interval):
    k8s = kubernetes.client.ExtensionsV1beta1Api()
    ingresses = k8s.list_ingress_for_all_namespaces().items
    services = k8s_ingresses_as_services(ingresses, ip=check_ip,
                                         interval=check_interval)
    try:
        click.echo('Reading {}'.format(service_file))
        with open(service_file, 'r') as f:
            current_json = f.read()
    except FileNotFoundError:
        current_json = None
    data = {'services': services}
    json_to_write = json.dumps(data, indent=2) + '\n'
    if json_to_write != current_json:
        click.echo('Writing {}...'.format(service_file))
        with open(service_file, 'w') as f:
            f.write(json_to_write)
        click.echo('Done!')
        sys.exit(3)
    else:
        click.echo('No changes')
        sys.exit(0)


def k8s_ingresses_as_services(ingresses, ip, interval):
    """
    Build a dict of Consul Service definitions based on k8s ingress resources.

    :param ingresses: Ingress resources to convert to service definitions.
    :type ingresses: list

    :param ip: IP against which to issue service checks.
    :type ip: str

    :param interval: Consul check interval at which to run service checks.
    :type interval: str

    :return: List of Consul services
    :rtype: list
    """
    services = []
    for ingress in ingresses:
        ingress_name = '{}/{}'.format(ingress.metadata.namespace,
                                      ingress.metadata.name)
        ann = ingress.metadata.annotations
        name = ann.get('consulk8s/service')
        if name is None or not name:
            continue

        port_ = ann.get('consulk8s/port', 80)
        try:
            port = int(port_)
        except ValueError:
            click.echo('Ingress "{}" bad port: {}'.format(ingress_name, port_),
                       err=True)
            sys.exit(1)

        check_host = ann.get('consulk8s/check_host')
        if check_host is None:
            try:
                check_host = ingress.spec.rules[0].host
            except KeyError:
                click.echo('Ingress "{}" has no host!'.format(ingress_name),
                           err=True)
                sys.exit(1)

        check_timeout = ann.get('consulk8s/check_timeout', '2s')
        check_path = ann.get('consulk8s/check_path', '/').lstrip('/')
        check_scheme = 'https' if port == 443 else 'http'

        services.append(OrderedDict((
            ('id', 'consulk8s_{}'.format(name)),
            ('service', name),
            ('port', port),
            ('checks', [
                OrderedDict((
                    ('name', '{} check'.format(name)),
                    ('notes', 'HTTP check host {} on port {} every {}'.format(
                        check_host, port, interval)),
                    ('http', '{}://{}:{}/{}'.format(check_scheme, ip, port,
                                                    check_path)),
                    ('interval', interval),
                    ('header', {'Host': [check_host]}),
                    ('timeout', check_timeout)
                ))
            ])
         )))
    return services


if __name__ == '__main__':
    cli()