consulk8s
=========

CLI tool that integrates Consul and Kubernetes.

Command: write-ingresses
------------------------

This command will query Kubernetes ingress resources for details to use to write
a Consul service configuration file.

This is useful on Kubernetes workers that are running ingress controllers or
other servers that might be proxying into ingress controllers, allowing
discovery of services exposed by Kubernetes.

.. code-block:: bash

    consulk8s write-ingresses -s /etc/consul.d/k8s_services.json

See ``consulk8s --help`` and ``consulk8s write-ingresses --help`` for more details.