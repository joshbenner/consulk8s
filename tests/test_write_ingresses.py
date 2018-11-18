import os
import sys
import itertools
import json

import pytest
import consulk8s

from click.testing import CliRunner


class MockModel(object):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture(name='testdir')
def get_test_dir():
    return os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(name='kubeconfig')
def get_kubeconfig(testdir):
    return "{}/kubeconfig.yml".format(testdir)


@pytest.fixture(name='servicefile')
def get_servicefile(tmpdir):
    return '{}/services.json'.format(tmpdir)


ingress_cases = (
    # Minimal ingress
    (
        [
            MockModel(
                metadata=MockModel(
                    name='foo-service',
                    namespace='default',
                    annotations={'consulk8s/service': 'foo'},
                ),
                spec=MockModel(rules=[MockModel(host='foo.test.tld')]),
                status=MockModel(load_balancer=MockModel(ingress=[
                    MockModel(ip='127.0.0.5')
                ]))
            )
        ],
        [
            {
                'id': 'consulk8s_foo',
                'name': 'foo',
                'port': 80,
                'checks': [
                    {
                        'name': 'foo check',
                        'notes': 'HTTP check foo.test.tld on port 80 every 30s',
                        'http': 'http://127.0.0.5:80/',
                        'header': {'Host': ['foo.test.tld']},
                        'interval': '30s',
                        'timeout': '2s'
                    }
                ]
            }
        ]
    ),

    # Minimal ingress with no loadBalancer ingress status ip.
    (
        [
            MockModel(
                metadata=MockModel(
                    name='foo-service',
                    namespace='default',
                    annotations={'consulk8s/service': 'foo'},
                ),
                spec=MockModel(rules=[MockModel(host='foo.test.tld')]),
                status=MockModel(load_balancer=MockModel(ingress=[
                    MockModel(ip=None)
                ]))
            )
        ],
        [
            {
                'id': 'consulk8s_foo',
                'name': 'foo',
                'port': 80,
                'checks': [
                    {
                        'name': 'foo check',
                        'notes': 'HTTP check foo.test.tld on port 80 every 30s',
                        'http': 'http://127.0.0.1:80/',
                        'header': {'Host': ['foo.test.tld']},
                        'interval': '30s',
                        'timeout': '2s'
                    }
                ]
            }
        ]
    ),

    # All annotations
    (
        [
            MockModel(
                metadata=MockModel(
                    name='bar-service',
                    namespace='default',
                    annotations={
                        'consulk8s/service': 'bar',
                        'consulk8s/address': '127.0.0.4',
                        'consulk8s/port': '123',
                        'consulk8s/check_host': 'bar.test.tld',
                        'consulk8s/check_path': '/bar',
                        'consulk8s/check_timeout': '5s'
                    },
                )
            )
        ],
        [
            {
                'id': 'consulk8s_bar',
                'name': 'bar',
                'port': 123,
                'checks': [
                    {
                        'name': 'bar check',
                        'notes': 'HTTP check bar.test.tld on port 123 every 30s',
                        'http': 'http://127.0.0.4:123/bar',
                        'header': {'Host': ['bar.test.tld']},
                        'interval': '30s',
                        'timeout': '5s'
                    }
                ]
            }
        ]
    ),

    # Ignore
    (
        [
            MockModel(
                metadata=MockModel(
                    name='baz-service',
                    namespace='default',
                    annotations={},
                )
            )
        ],
        []
    )
)


@pytest.mark.parametrize('ingresses,expected', ingress_cases)
def test_ingress_to_service(ingresses, expected):
    s = consulk8s.k8s_ingresses_as_services(ingresses, '127.0.0.1', '30s')
    generated = json.loads(json.dumps(s))
    assert generated == expected


def write_test_service_file(ingresses, monkeypatch, kubeconfig, servicepath):
    monkeypatch.setattr(consulk8s, 'get_k8s_ingresses', lambda: ingresses)
    runner = CliRunner()
    return runner.invoke(consulk8s.cli, [
        '-k', kubeconfig, '-c', 'test',
        'write-ingresses', '-s', servicepath,
        '--code-when-changed', '3'
    ])


def test_write_ingresses_cli(monkeypatch, kubeconfig, servicefile):
    ingresses = list(itertools.chain(*(c[0] for c in ingress_cases)))
    expected = {
        'services': list(itertools.chain(*(c[1] for c in ingress_cases)))
    }
    result = write_test_service_file(ingresses, monkeypatch, kubeconfig,
                                     servicefile)
    assert result.exit_code == 3

    with open(servicefile, 'r') as f:
        parsed = json.loads(f.read())
    assert parsed == expected


def test_write_ingresses_no_change(monkeypatch, kubeconfig, servicefile):
    ingresses = list(itertools.chain(*(c[0] for c in ingress_cases)))
    write_test_service_file(ingresses, monkeypatch, kubeconfig, servicefile)
    result = write_test_service_file(ingresses, monkeypatch, kubeconfig,
                                     servicefile)
    assert result.exit_code == 0


def test_bad_port(monkeypatch, kubeconfig, servicefile):
    ingresses = [
        MockModel(
            metadata=MockModel(
                name='bad-port-service',
                namespace='default',
                annotations={
                    'consulk8s/service': 'bad-port',
                    'consulk8s/port': 'this is not a port number'
                },
            ),
            status=MockModel(load_balancer=MockModel(ingress=[
                MockModel(ip='127.0.0.5')
            ]))
        )
    ]
    monkeypatch.setattr(consulk8s, 'get_k8s_ingresses', lambda: ingresses)
    runner = CliRunner()
    result = runner.invoke(consulk8s.cli, [
        '-k', kubeconfig, '-c', 'test',
        'write-ingresses', '-s', servicefile,
    ])
    assert result.exit_code == 1
    assert 'bad port' in result.output


def test_no_host(monkeypatch, kubeconfig, servicefile):
    ingresses = [
        MockModel(
            metadata=MockModel(
                name='no-host',
                namespace='default',
                annotations={
                    'consulk8s/service': 'no-host',
                },
            ),
            spec=MockModel(rules=[]),
            status=MockModel(load_balancer=MockModel(ingress=[
                MockModel(ip='127.0.0.5')
            ]))
        )
    ]
    monkeypatch.setattr(consulk8s, 'get_k8s_ingresses', lambda: ingresses)
    runner = CliRunner()
    result = runner.invoke(consulk8s.cli, [
        '-k', kubeconfig, '-c', 'test',
        'write-ingresses', '-s', servicefile,
    ])
    assert result.exit_code == 1
    assert 'no host' in result.output


def test_write_ingresses_with_command(monkeypatch, kubeconfig, servicefile):
    ingresses = list(itertools.chain(*(c[0] for c in ingress_cases)))
    monkeypatch.setattr(consulk8s, 'get_k8s_ingresses', lambda: ingresses)
    runner = CliRunner()
    result = runner.invoke(consulk8s.cli, [
        '-k', kubeconfig, '-c', 'test',
        'write-ingresses', '-s', servicefile,
        '--change-command', '{} --version'.format(sys.executable)
    ])
    v = sys.version_info
    assert '{}.{}.{}'.format(v.major, v.minor, v.micro) in result.output
