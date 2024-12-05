# import pytest
# import requests
# from testcontainers.core.container import DockerContainer
# from testcontainers.core.waiting_utils import wait_for_logs

# TRIPLESTORE_IMAGE = 'stain/jena-fuseki:latest'
# TRIPLESTORE_PASSWORD = 'password'

# @pytest.fixture(scope="module")
# def triplestore():
#     """Start Fuseki container as a fixture."""
#     # with DockerContainer(TRIPLESTORE_IMAGE) as container:
#     container = DockerContainer(TRIPLESTORE_IMAGE)
#     container.with_exposed_ports(3030)
#     container.with_env("ADMIN_PASSWORD", TRIPLESTORE_PASSWORD)
#     container.start()
#     delay = wait_for_logs(container, "Fuseki is available")
#     base_url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(3030)}"
#     print(f"Fuseki started in {delay:.0f}s at {base_url}")
#     # print(container.get_logs())
#     yield base_url

# def test_sparql_query(triplestore):
#     """Test SPARQL query execution."""
#     # sparql_endpoint = f"{triplestore_container}/repositories/{GRAPHDB_REPO_NAME}"

#     # Insert a sample RDF triple into the repository
#     insert_query = """PREFIX ex: <http://example.org/>
#     INSERT DATA { ex:subject ex:predicate ex:object . }
#     """
#     resp = requests.post(
#         f"{triplestore}",
#         data={"update": insert_query},
#         auth=('admin', TRIPLESTORE_PASSWORD),
#     )
#     print(resp.text)
#     resp.raise_for_status()

#     query = """SELECT ?s ?p ?o WHERE {
#         ?s ?p ?o .
#     }"""
#     resp = requests.post(f"{triplestore}", data={"query": query}, headers={"Accept": "application/sparql-results+json"})
#     resp.raise_for_status()

#     # Check if the triple was inserted and queried correctly
#     print(resp.text)
#     result = resp.json()
#     assert len(result['results']['bindings']) == 1
#     assert result['results']['bindings'][0]['s']['value'] == 'http://example.org/subject'
#     assert result['results']['bindings'][0]['p']['value'] == 'http://example.org/predicate'
#     assert result['results']['bindings'][0]['o']['value'] == 'http://example.org/object'
