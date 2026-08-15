import dataclasses
from uuid import UUID, uuid4

import pytest

from braunprices.domain.errors import DomainError, ListingNotInProductError
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.store_slug import StoreSlug

VALID_EAN = EAN("4006381333931")


def listing(
    *,
    store: str = "loja-exemplo",
    external_id: str = "12345",
    listing_id: UUID | None = None,
    is_active: bool = True,
) -> StoreListing:
    return StoreListing(
        listing_id=listing_id or uuid4(),
        store_slug=StoreSlug(store),
        external_id=external_id,
        url=f"https://{store}.pt/p/{external_id}",
        is_active=is_active,
    )


def product(**kwargs: object) -> Product:
    defaults: dict[str, object] = {
        "product_id": uuid4(),
        "canonical_name": "Máquina de café",
    }
    defaults.update(kwargs)
    return Product(**defaults)  # type: ignore[arg-type]


# -- casamento entre lojas -------------------------------------------------


def test_a_product_without_ean_exists_but_does_not_cross_stores() -> None:
    # Casamento por semelhança de texto está fora de âmbito por decisão explícita:
    # dois nomes parecidos não são o mesmo produto, e um casamento errado contamina
    # o histórico de ambos.
    assert product().participates_in_cross_store_matching is False


def test_a_product_with_ean_participates_in_matching() -> None:
    assert product(ean=VALID_EAN).participates_in_cross_store_matching is True


# -- referências de loja ---------------------------------------------------


def test_adds_listings_from_different_stores() -> None:
    item = product(ean=VALID_EAN)
    item.add_listing(listing(store="loja-exemplo"))
    item.add_listing(listing(store="outra-loja"))
    assert len(item.listings) == 2


def test_refuses_the_same_reference_twice_in_the_same_store() -> None:
    # Duas referências iguais produziriam duas séries de observações para a mesma
    # página, e o histórico passaria a contar cada preço duas vezes.
    item = product()
    item.add_listing(listing(store="loja-exemplo", external_id="12345"))
    with pytest.raises(DomainError, match="já tem a referência"):
        item.add_listing(listing(store="loja-exemplo", external_id="12345"))


def test_the_same_external_id_in_another_store_is_a_different_reference() -> None:
    item = product()
    item.add_listing(listing(store="loja-exemplo", external_id="12345"))
    item.add_listing(listing(store="outra-loja", external_id="12345"))
    assert len(item.listings) == 2


def test_construction_refuses_duplicated_references() -> None:
    duplicated = [
        listing(store="loja-exemplo", external_id="12345"),
        listing(store="loja-exemplo", external_id="12345"),
    ]
    with pytest.raises(DomainError, match="repetida"):
        product(listings=duplicated)


def test_finds_a_listing_by_its_identifier() -> None:
    target = listing()
    item = product(listings=[target])
    assert item.listing(target.listing_id) is target


def test_asking_for_a_listing_that_is_not_there_fails_explicitly() -> None:
    item = product()
    with pytest.raises(ListingNotInProductError):
        item.listing(uuid4())


# -- desativação -----------------------------------------------------------


def test_deactivating_a_listing_keeps_it_in_the_product() -> None:
    # Não se apaga: as observações já recolhidas continuam a referir-se a ela. Uma
    # referência inativa deixa de ser visitada, não deixa de ter passado.
    target = listing()
    item = product(listings=[target])
    item.deactivate_listing(target.listing_id)
    assert len(item.listings) == 1
    assert item.listing(target.listing_id).is_active is False


def test_only_active_listings_are_visited() -> None:
    active, inactive = listing(external_id="1"), listing(external_id="2")
    item = product(listings=[active, inactive])
    item.deactivate_listing(inactive.listing_id)
    assert [entry.external_id for entry in item.active_listings] == ["1"]


def test_deactivating_an_unknown_listing_fails_explicitly() -> None:
    with pytest.raises(ListingNotInProductError):
        product().deactivate_listing(uuid4())


# -- invariantes de StoreListing -------------------------------------------


def test_a_listing_needs_an_external_id() -> None:
    with pytest.raises(DomainError, match="external_id"):
        listing(external_id="   ")


def test_a_listing_needs_an_absolute_url() -> None:
    with pytest.raises(DomainError, match="URL absoluto"):
        StoreListing(
            listing_id=uuid4(),
            store_slug=StoreSlug("loja-exemplo"),
            external_id="12345",
            url="/p/12345",
        )


def test_a_listing_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        listing().is_active = False  # type: ignore[misc]


def test_a_product_needs_a_name() -> None:
    with pytest.raises(DomainError, match="canonical_name"):
        product(canonical_name="   ")


def test_finds_a_listing_that_is_not_the_first_one() -> None:
    first, second = listing(external_id="1"), listing(external_id="2")
    item = product(listings=[first, second])
    assert item.listing(second.listing_id) is second


def test_deactivates_a_listing_that_is_not_the_first_one() -> None:
    first, second = listing(external_id="1"), listing(external_id="2")
    item = product(listings=[first, second])
    item.deactivate_listing(second.listing_id)
    assert item.listing(first.listing_id).is_active is True
    assert item.listing(second.listing_id).is_active is False
