"""Produto e as suas referências em lojas.

``Product`` tem identidade própria do sistema, não herdada de nenhuma loja: a mesma
máquina de café é um produto, esteja listada em uma loja ou em cinco. ``StoreListing``
é a forma como uma loja concreta o refere.
"""

from dataclasses import dataclass, field
from uuid import UUID

from braunprices.domain.errors import DomainError, ListingNotInProductError
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.store_slug import StoreSlug


@dataclass(frozen=True, slots=True)
class StoreListing:
    """Uma referência de produto dentro de uma loja.

    ``external_id`` é o identificador que a loja usa (SKU, referência interna). É
    opaco: não se interpreta, só se compara.
    """

    listing_id: UUID
    store_slug: StoreSlug
    external_id: str
    url: str
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.external_id.strip():
            raise DomainError("StoreListing precisa de um external_id.")
        if not self.url.startswith(("http://", "https://")):
            raise DomainError(f"url={self.url!r} não é um URL absoluto.")
        object.__setattr__(self, "external_id", self.external_id.strip())

    def deactivated(self) -> "StoreListing":
        """Devolve a mesma referência marcada como inativa."""
        return StoreListing(
            listing_id=self.listing_id,
            store_slug=self.store_slug,
            external_id=self.external_id,
            url=self.url,
            is_active=False,
        )


@dataclass(slots=True)
class Product:
    """Agregado que reúne as referências da mesma coisa em lojas diferentes."""

    product_id: UUID
    canonical_name: str
    ean: EAN | None = None
    listings: list[StoreListing] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.canonical_name.strip():
            raise DomainError("Product precisa de um canonical_name.")
        self.canonical_name = self.canonical_name.strip()
        seen: set[tuple[str, str]] = set()
        for listing in self.listings:
            key = (listing.store_slug.value, listing.external_id)
            if key in seen:
                raise DomainError(f"Referência repetida no produto: {key}.")
            seen.add(key)

    @property
    def participates_in_cross_store_matching(self) -> bool:
        """Indica se este produto pode ser casado com referências de outras lojas.

        Sem EAN, não pode. O casamento por semelhança de texto está fora de âmbito por
        decisão explícita: dois produtos com nomes parecidos não são o mesmo produto, e
        um casamento errado contamina o histórico de ambos.
        """
        return self.ean is not None

    def add_listing(self, listing: StoreListing) -> None:
        """Junta uma referência de loja ao produto.

        Recusa duplicados no par ``(loja, external_id)``: duas referências iguais
        produziriam duas séries de observações para a mesma página.
        """
        key = (listing.store_slug.value, listing.external_id)
        for existing in self.listings:
            if (existing.store_slug.value, existing.external_id) == key:
                raise DomainError(f"O produto já tem a referência {key}.")
        self.listings.append(listing)

    def listing(self, listing_id: UUID) -> StoreListing:
        """Devolve a referência com este identificador."""
        for existing in self.listings:
            if existing.listing_id == listing_id:
                return existing
        raise ListingNotInProductError(
            f"O produto {self.product_id} não tem o listing {listing_id}."
        )

    def deactivate_listing(self, listing_id: UUID) -> None:
        """Marca uma referência como inativa, sem a remover.

        Não se apaga: as observações já recolhidas continuam a existir e a referir-se a
        ela. Uma referência inativa deixa de ser visitada, não deixa de ter passado.
        """
        for index, existing in enumerate(self.listings):
            if existing.listing_id == listing_id:
                self.listings[index] = existing.deactivated()
                return
        raise ListingNotInProductError(
            f"O produto {self.product_id} não tem o listing {listing_id}."
        )

    @property
    def active_listings(self) -> list[StoreListing]:
        """Referências que continuam a ser visitadas na recolha."""
        return [listing for listing in self.listings if listing.is_active]
