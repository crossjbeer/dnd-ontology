# An Ontology and Knowledge Graph for Dungeons and Dragons (DnD) built with OwlReady2 and RDFLib.

## Corpus
Our corpus is based on abstract, handwritten homebrew DnD materials.
I used GPT5.4 to produce a YAML-formatted "Lore" document for ingestion into the ontology.
Limitations of this approach are discussed in data/lore.yaml.

## Ontology
The ontology is built under the OWL 2 DL profile of the OWL 2 formal standard.
It is minimal, focusing on Locations, Characters, Factions, and Items, while using Quests to link them in material ways. 
I built the ontology to demonstrate the use of several ObjectProperties, class hierarchies, and formalization features of the OwlReady2 package.

## Knowledge Graph
Our lore is ingested in two passes, first to determine unique individuals and second to apply properties to those individuals. 
This creates the initial triplet store over which we infer, using the HermiT reasoner.
Finally, with the inferred triplet store built, one may query using RDFLib and SPARQL from the commandline.


### Reasoner Caveat
The choice of ontology standard influences choice of reasoner.
Other choices of reasoner exist, including Pellet or faCT++.
In this version of OwlReady2 (0.5) Pellet is implemented in Java25, while HermiT should run 
A faCT++ integration requires moving away from OwlReady2, which is another good project.

## Requirements: 
### Java Requirement: 
OWL reasoning with HermiT requires Java 8+.

Check your version:

    java -version

If Java is not installed, download OpenJDK from:
https://adoptium.net

### Python Requirement: 
OwlReady2 and RDFLib require Python 3.10