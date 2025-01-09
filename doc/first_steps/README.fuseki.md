git clone https://github.com/stain/jena-docker.git
cd jena-docker/
docker build -t jena-fuseki jena-fuseki

export FUSEKI_DIR=$HOME/scratch/fuseki # FIXME: update as required

mkdir -p $FUSEKI_DIR
cp $KGSTEWARD_ROOT_DIR/doc/first_steps/fuseki.config.ttl $FUSEKI_DIR

export FUSEKI_USERNAME=admin               # update as required
export FUSEKI_PASSWORD=pw123               # update as required
# --platform=linux/amd64
docker run \
	-p 3030:3030 \
	-e ADMIN_PASSWORD=$FUSEKI_PASSWORD \
	-e JVM_ARGS=-Xmx4g \
	-e FUSEKI_CONF=/fuseki/fuseki.config.ttl \
	-v $FUSEKI_DBDIR:/fuseki \
	jena-fuseki


brew install fuseki
export FUSEKI_DIR=~/scratch/fuseki # FIXME: fix it
( cd $FUSEKI_DIR && fuseki-server --config $KGSTEWARD_ROOT_DIR/doc/first_steps/fuseki.config.ttl )


uv run kgsteward doc/first_steps/fuseki.yaml -ICV

