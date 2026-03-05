from __future__ import annotations

from pathlib import Path 
from typing import Optional 

from owlready2 import (
    get_ontology, 
    Thing,
    ObjectProperty,
    DataProperty,
    FunctionalProperty,
    TransitiveProperty,
    SymmetricProperty,
    Ontology,
    default_world,
    AllDisjoint
)

BASE_IRI = "http://example.org/dnd/onto" # 'url' naming the ontology - not necessarily a real URL, but should be unique to avoid conflicts with other ontologies.

def build_ontology(
        out_path: str | Path = Path("out/dnd_world.owl"),
        base_iri: str = BASE_IRI,
        overwrite: bool = False
    ) -> Ontology:

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True) # ensure the output directory exists

    if out_path.exists() and not overwrite:
        raise FileExistsError(f"Output file {out_path} already exists. Set overwrite=True to overwrite it.")
    
    onto = get_ontology(base_iri)

    with onto: 
        # ------------------
        # CLASSES (TBox)
        # ------------------

        # Fairly standard class hierarchy for a DnD world.
        class WorldEntity(Thing):
            pass 

        class Location(WorldEntity):
            pass 

        class Region(Location):
            pass 

        class City(Location):
            pass 

        class Dungeon(Location):
            pass 

        class Faction(WorldEntity):
            pass 

        class AdventuringParty(Faction):
            pass

        class Character(WorldEntity):
            pass 

        class NPC(Character): 
            pass 

        class PlayerCharacter(Character):
            pass 

        class Item(WorldEntity):
            pass 

        class Weapon(Item):
            pass 

        class Artifact(Item):
            pass 

        class Potion(Item):
            pass 

        class Quest(WorldEntity):
            pass 

        class Species(WorldEntity):
            pass 

        class ClassRole(WorldEntity):
            pass 

        # ------------------
        # OBJECT PROPERTIES 
        # ------------------

        # Some internal debate as to whether make this Transitive. 
        # It comes down to whether we want to allow for reasoning about indirect locations for all entities, or whether we want to require explicit assertions for each level of location.
        # This is why we include the 'partOf' relationship for locations - to allow for reasoning about indirect locations without making the 'locatedIn' relationship itself transitive.
        class locatedIn(ObjectProperty):
            """Where any entity is located"""
            domain = [WorldEntity]
            range = [Location]

        class hasLocation(ObjectProperty):
            """Inverse of locatedIn (location hasLocation entity)"""
            domain = [Location]
            range = [WorldEntity]

        locatedIn.inverse_property = hasLocation

        class partOf(ObjectProperty, TransitiveProperty):
            """A location is part of another location (city partOf region)"""
            domain = [Location]
            range = [Location]

        class contains(ObjectProperty):
            """Inverse of partOf (region contains city). No need to explicitly define domain/range here as domain and range are symmetric with partOf, 
            and OWL reasoners should be able to infer this from the inverse property definition."""

        contains.inverse_property = partOf 

        class memberOf(ObjectProperty):
            """(character memberOf faction)"""
            domain = [Character]
            range = [Faction]

        class hasMember(ObjectProperty):
            """Inverse of memberOf (faction hasMember character)"""
            domain = [Faction]
            range = [Character] # Want to explicitly define domain/range here to avoid issues with inverse properties and OWL reasoners

        hasMember.inverse_property = memberOf

        class rules(ObjectProperty): # Optionally could add a FunctionalProperty here to enforce that a character can only rule one faction at a time
        # class rules(ObjectProperty, FunctionalProperty):
            """(character rules faction)"""
            domain = [Character]
            range = [Faction]

        class ruledBy(ObjectProperty):
            """Inverse of rules (faction ruledBy character)"""
            domain = [Faction]
            range = [Character]

        ruledBy.inverse_property = rules

        class allyOf(ObjectProperty, SymmetricProperty):
            """(faction allyOf faction)"""
            domain = [Faction]
            range = [Faction]   

        class enemyOf(ObjectProperty, SymmetricProperty):
            """(faction enemyOf faction)"""
            domain = [Faction]
            range = [Faction]

        # Quests are how we link together characters, locations, and items in a meaningful way. 
        class givesQuest(ObjectProperty):
            """(entity givesQuest quest)"""
            domain = [WorldEntity]
            range = [Quest]

        class questGiver(ObjectProperty):
            """Inverse of givesQuest (quest questGiver entity)"""
            domain = [Quest]
            range = [WorldEntity]
        questGiver.inverse_property = givesQuest

        # Purposefully not building inverse for these properties to allow for more flexible reasoning about quest targets, requirements, and rewards without needing to explicitly define inverse relationships for each entity type.
        class targetsLocation(ObjectProperty):
            """(quest targetsLocation location)"""
            domain = [Quest]
            range = [Location]

        class requiresItem(ObjectProperty):
            """(quest requiresItem item)"""
            domain = [Quest]
            range = [Item]

        class rewardsItem(ObjectProperty):
            """(quest rewardsItem item)"""
            domain = [Quest]
            range = [Item]

        class hasSpecies(ObjectProperty):
            """(character hasSpecies species)"""
            domain = [Character]
            range = [Species]

        class hasClass(ObjectProperty):
            """(character hasClass class)"""
            domain = [Character]
            range = [ClassRole]

        # ------------------
        # DATA PROPERTIES
        # ------------------

        class hasName(DataProperty, FunctionalProperty):
            """Name of any entity"""
            domain = [WorldEntity]
            range = [str]

        class hasAlignment(DataProperty, FunctionalProperty):
            """Alignment of a character or faction (e.g. 'Chaotic Good')"""
            domain = [Character]
            range = [str]

        # One good reason to split Character into NPC/PlayerCharacter is to allow for properties that only apply to one type of character. 
        class hasLevel(DataProperty, FunctionalProperty):
            """Level of a character or item"""
            domain = [PlayerCharacter]
            range = [int]

        class hasCR(DataProperty, FunctionalProperty):
            """Challenge Rating of a location or item"""
            domain = [NPC]
            range = [float]

        class hasPopulation(DataProperty, FunctionalProperty):
            """Population of a location"""
            domain = [Location]
            range = [int]

        AllDisjoint([Location, Faction, Character, Item, Quest, Species, ClassRole]) # Assert that top-level classes are disjoint
    
        # ------------------
        # METADATA
        # ------------------
        onto.metadata.comment.append(
            "D&D World Ontology - A simple ontology for representing entities and relationships in a fictional world."
        )

    onto.save(file=str(out_path), format="rdfxml") # Saving in RDF/XML format, which is widely supported by OWL tools and reasoners. 

    return onto 

def main() -> None: 
    onto = build_ontology() 
    print("Ontology Built")
    print("IRI:", onto.base_iri)
    print("Saved to: out/dnd_world.owl")
    with onto: 
        print("Classes:", list(onto.classes()))
        print("Object Properties:", list(onto.object_properties()))
        print("Data Properties:", list(onto.data_properties()))

if __name__ == "__main__":
    main()