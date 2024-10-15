# First steps with GraphDB

1. Clone kgsteward from GitHub, Create an environement variable that point to its root dir: 

```
[change dir to where you like to clone from github]
git clone https://github.com/sib-swiss/kgsteward.git kgsteward
export KGSTEWARD_ROOT_DIR=`pwd`/kgsteward
```

This environment variable `KGSTEWARD_ROOT_DIR` will be used through all the examples.

2.  Install (the free version of) GraphDB from [Ontotext website](https://www.ontotext.com/products/graphdb/download/?ref=menu), following the vendor instructions. Launch GraphDB, using the application icons or the commend line. By default, the user interface of GraphDB becomes available at http://localhost:7200.

3. In another terminal with $KGSTEWARD_ROOT_DIR defined as above, and after kgsteward has been installed ([instructions here](https://github.com/sib-swiss/kgsteward)), run the following commands to rewrite and populate the BEATLE_DEMO repository according to the content of `first_steps_fuseki.yaml`

```
cd $KGSTEWARD_ROOT_DIR/example/first_steps_graphdb
kgsteward first_steps_graphdb.yaml -I # rewrite repository
kgsteward first_steps_graphdb.yaml -C # populate repository
```

The file `first_steps_graphdb.yaml` contains:

```
store:
  server_brand:  fuseki
  server_url:    http://localhost:3030
  server_config: config-fuseki-tdb2.ttl 
repository_id: BEATLES_DEMO
graphs:
  - name: beatles
    url:
      - https://raw.githubusercontent.com/stardog-union/stardog-tutorials/refs/heads/master/music/beatles.ttl
```

which describe what is the server `store:` and how to populate its `graphs:`.


4. Run a SPARQL query to verify that the server is accessible and returns the expected results:

```
curl \
	-H "Accept: text" \
	--data-urlencode "query=SELECT ?artist WHERE{ ?artist a <http://stardog.com/tutorial/SoloArtist> } ORDER BY ?artist" \
	http://localhost:7200/repositories/BEATLES_DEMO
```

which should print out:

```
http://stardog.com/tutorial/George_Harrison
http://stardog.com/tutorial/John_Lennon
http://stardog.com/tutorial/Paul_McCartney
http://stardog.com/tutorial/Ringo_Starr
```

Congratulations: you have populated a graphdb repository using kgsteward :-)









