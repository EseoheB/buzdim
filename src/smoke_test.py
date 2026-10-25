from owlready2 import get_ontology, Thing, sync_reasoner, sync_reasoner_pellet

# Create a tiny test ontology with one class and one individual
onto = get_ontology("http://www.example.org/test.owl#")
with onto:
    class Server(Thing):
        pass
    server_a = Server("server_a")

# Run both reasoners. If Java is missing, this is where it fails.
with onto:
    sync_reasoner()
print("HermiT works")

with onto:
    sync_reasoner_pellet()
print("Pellet works")
