from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from sqlalchemy.orm import validates
from models.database import Base


class Store(Base):
    __tablename__ = "stores"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(150), nullable=False, index=True)
    local_number  = Column(String(60), nullable=True)   # ej: "104", "S/N" — ampliado de 20 a 60 (lección aprendida: un valor de 25 caracteres causó un error 500 real en una importación)
    floor         = Column(String(60), nullable=False)
    category      = Column(String(80), nullable=False)
    description   = Column(Text, nullable=True)
    schedule      = Column(String(200), nullable=True)
    phone         = Column(String(60), nullable=True)
    location_hint = Column(String(200), nullable=True)
    tags          = Column(String(300), nullable=True)
    photo_url     = Column(String(500), nullable=True)  # link a una foto del local (externo — ver nota en el panel)
    extra_info    = Column(Text, nullable=True)  # campo libre: carta, cartelera, o cualquier info adicional del local
    # LINK de catálogo/carta digital del local (Instagram, web, wa.me/c/…,
    # catálogo en línea). Cuando un local NO manda la carta como PDF/foto
    # sino como enlace, se guarda aquí. Si el cliente pide "la carta / el
    # menú / el catálogo", Any le envía ESTE link directamente — el link
    # cuenta como carta, no solo los PDF o las imágenes.
    catalogo_link = Column(String(500), nullable=True)
    active        = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    # ── PROTECCIÓN AUTOMÁTICA DE LONGITUD (red de seguridad definitiva) ──
    # Estos validadores se ejecutan SOLOS cada vez que se asigna un valor
    # a un campo con límite, sin importar de dónde venga (importador CSV,
    # Excel, edición manual, etc.). Si un valor es más largo que la
    # columna, lo recorta automáticamente en vez de dejar que la base de
    # datos lance el error "value too long". Es IMPOSIBLE que ese error
    # vuelva a ocurrir por estos campos.
    _LIMITES = {
        "name": 150, "local_number": 60, "floor": 60, "category": 80,
        "schedule": 200, "phone": 60, "location_hint": 200, "tags": 300,
        "photo_url": 500, "catalogo_link": 500,
    }

    @validates("name", "local_number", "floor", "category", "schedule",
               "phone", "location_hint", "tags", "photo_url", "catalogo_link")
    def _recortar_campo(self, key, value):
        if value is None:
            return value
        limite = self._LIMITES.get(key)
        s = str(value)
        if limite and len(s) > limite:
            return s[:limite]
        return s

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "local_number": self.local_number,
            "floor": self.floor,
            "category": self.category,
            "description": self.description,
            "schedule": self.schedule,
            "phone": self.phone,
            "location_hint": self.location_hint,
            "tags": self.tags,
            "photo_url": self.photo_url,  # respaldo — se mantiene por compatibilidad con fotos cargadas antes de la galería
            "extra_info": self.extra_info,
            "catalogo_link": self.catalogo_link,
            "active": self.active,
            "photos": [p.to_dict() for p in sorted(self.photos, key=lambda p: p.created_at)] if self.photos else [],
        }

    def get_photo_by_label(self, label: str) -> str | None:
        """
        Busca la foto con esa etiqueta específica en la galería (ej.
        "carta" cuando preguntan por el menú). Si no hay ninguna con esa
        etiqueta mas sí existe una "portada", la usa como respaldo. Si
        la galería está vacía por completo, cae al campo viejo photo_url.
        """
        for p in self.photos:
            if p.label == label:
                return p.photo_url
        for p in self.photos:
            if p.label == "portada":
                return p.photo_url
        return self.photo_url

    def whatsapp_link(self) -> str | None:
        """Genera el link wa.me a partir del teléfono, para transferencias de domicilio."""
        if not self.phone:
            return None
        digits = "".join(c for c in self.phone if c.isdigit())
        if not digits:
            return None
        if not digits.startswith("57") and len(digits) == 10:
            digits = "57" + digits
        return f"https://wa.me/{digits}"

    def carta_como_link(self) -> str | None:
        """
        Devuelve el link de catálogo SOLO si el local no tiene una foto de
        carta subida (porque en ese caso la carta se manda como imagen).
        Sirve para que, cuando no hay foto pero sí hay enlace, Any igual
        pueda entregar 'la carta' como link en vez de decir que no la tiene.
        """
        tiene_foto_carta = any(getattr(p, "label", None) == "carta" for p in (self.photos or []))
        if tiene_foto_carta:
            return None
        return self.catalogo_link or None

    def to_rag_text(self) -> str:
        parts = [
            f"ID: {self.id}",
            f"Tienda: {self.name}",
            f"Local: {self.local_number or 'S/N'}",
            f"Categoría: {self.category}",
        ]
        # El piso solo se incluye si está definido — nunca "Por confirmar"
        # (para que la IA no se lo diga al cliente).
        if self.floor and self.floor.strip().lower() != "por confirmar":
            parts.insert(3, f"Piso: {self.floor}")
        if self.description:
            parts.append(f"Descripción: {self.description}")
        if self.schedule:
            parts.append(f"Horario: {self.schedule}")
        if self.phone:
            parts.append(f"Teléfono: {self.phone}")
            link = self.whatsapp_link()
            if link:
                parts.append(f"Link de WhatsApp del local (úsalo si el cliente quiere contactarlo directo): {link}")
        if self.location_hint:
            parts.append(f"Ubicación: {self.location_hint}")
        if self.tags:
            parts.append(f"Palabras clave: {self.tags}")
        if self.extra_info:
            parts.append(f"Información adicional: {self.extra_info}")
        if self.catalogo_link:
            parts.append(
                "CARTA/CATÁLOGO del local (ESTE enlace ES la carta/menú/catálogo "
                "de este local; si el cliente pide la carta, el menú o el catálogo, "
                f"envíaselo tal cual como respuesta): {self.catalogo_link}"
            )
        # Si esta tienda es el Cine y tiene funciones cargadas, se
        # incluyen aquí mismo — así, cuando alguien pregunte por el
        # cine, la cartelera actual viene incluida automáticamente,
        # sin necesitar un sistema aparte.
        funciones_activas = [f for f in self.cine_funciones if f.active]
        if funciones_activas:
            parts.append("Cartelera actual: " + " | ".join(f.to_rag_text() for f in funciones_activas))
        return " | ".join(parts)