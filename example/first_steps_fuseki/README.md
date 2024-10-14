# First steps with Fuseki

1. Clone kgsteward from GitHub and create an environement variable that point to its root dir: 

```
[change dir to where you like to clone from github]
git clone https://github.com/sib-swiss/kgsteward.git
export GITHUB_KGSTEWARD_DIR=`pwd`/kgsteward
```

2. Install fuseki locally. For example, with homebrew on OSX:

```
brew install fuseki
```

3. Launch the fuseki server with the configuration file supplied for this example:

```
fuseki-server --localhost --port 3030 --config=$GITHUB_KGSTEWARD_DIR/example/first_steps_fuseki/config-fuseki-tdb2.ttl
```

The fuseki web interface becomes available at `http://localhost:3030`

The file `config-fuseki-tdb2.ttl` contains the configuration of the repository: 
it is named "BEATLES_DEMO", 
it has read/write permissions,
it saves its internal files in the TDB2 sub-directory (declared in .gitignore),
and importantly for kgsteward, the union of all graphs is set as querying default.

Please refer to the [fuseki documentation](https://jena.apache.org/documentation/fuseki2) for more about fuseki configuration.

5. In another terminal with $GITHUB_KGSTEWARD_DIR defined as above, and after kgsteward has been installed, run the following commands to rewrite and populate the BEATLE_DEMO repository according to the content of `first_steps_fuseki.yaml`

```
cd $GITHUB_KGSTEWARD_DIR/example/first_steps_fuseki
kgsteward first_steps_fuseki.yaml -I # rewrite repository
kgsteward first_steps_fuseki.yaml -C # populate repository
```

The file `first_steps_fuseki.yaml` contains the following:

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

which explain what is the server `store:` and how to populate it `graphs`.

6. Run a SPARQL query to verify that the server is accessible and contains something:

```
curl \
	-H "Accept: text" \
	--data-urlencode "query=SELECT ?artist WHERE{ ?artist a <http://stardog.com/tutorial/SoloArtist> } ORDER BY ?artist" \
	http://localhost:3030/BEATLES_DEMO/sparql
```

which should return:

```
http://stardog.com/tutorial/George_Harrison
http://stardog.com/tutorial/John_Lennon
http://stardog.com/tutorial/Paul_McCartney
http://stardog.com/tutorial/Ringo_Starr
```

Congratulations: you populate a fuseki repository using kgsteward :-)







