consulk8s
=========

|Status|

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

Annotations on Ingress objects:

* ``consulk8s/service`` - Name of Consul service to create for Ingress.
* ``consulk8s/address`` - Address/IP to announce in Consul service. Defaults to Ingress loadBalancer IP.
* ``consulk8s/port`` - Port to announce in Consul service. Defaults to 80.
* ``consuk8s/check_host`` - Host header to set in Consul health checks. Uses first hostname found in Ingress if none specified.
* ``consulk8s/check_timeout`` - Timeout for Consul health check. Defaults to 2s.
* ``consulk8s/check_path`` - Path segment of URL to make HTTP health check request. Defaults to '/'.
* ``consulk8s/tls_skip_verify`` - Skip TLS verification. Consul defaults to false.
* ``consulk8s/check_scheme`` - HTTP scheme, either 'http' or 'https' - Allows setting SSL on ports other than 443

.. |Status| image:: https://img.shields.io/travis/joshbenner/consulk8s.svg?
   :target: https://travis-ci.org/joshbenner/consulk8s
