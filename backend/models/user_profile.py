"""
models/user_profile.py  ← NUEVO archivo
Guarda el perfil resumido de cada usuario.
El job de profiling.py lo actualiza cada 7 días.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from models.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id           = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    user_name    = Column(String(100), nullable=True)

    # Resumen generado por IA a partir de conversaciones pasadas
    summary      = Column(Text, nullable=True)
    # ej: "Usuario frecuente. Le interesa ropa deportiva (Nike, Adidas).
    #      Consulta domicilios los viernes. Horario preferido: noches."

    # Datos estructurados extraídos
    interests    = Column(String(500), nullable=True)   # "ropa deportiva,comida,cine"
    fav_stores   = Column(String(300), nullable=True)   # "Nike Store,McDonald's"
    visit_freq   = Column(String(20),  nullable=True)   # "ocasional","regular","frecuente"
    total_msgs   = Column(Integer, default=0)

    last_profiled = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    def to_context_string(self) -> str:
        """
        Devuelve el perfil como string para incluir en el prompt de la IA.
        """
        parts = []
        if self.summary:
            parts.append(self.summary)
        if self.interests:
            parts.append(f"Intereses: {self.interests}")
        if self.fav_stores:
            parts.append(f"Tiendas favoritas: {self.fav_stores}")
        if self.visit_freq:
            parts.append(f"Frecuencia de visita: {self.visit_freq}")
        return " | ".join(parts) if parts else ""

    def to_dict(self):
        return {
            "phone_number": self.phone_number,
            "user_name":    self.user_name,
            "summary":      self.summary,
            "interests":    self.interests,
            "fav_stores":   self.fav_stores,
            "visit_freq":   self.visit_freq,
            "total_msgs":   self.total_msgs,
            "last_profiled": str(self.last_profiled) if self.last_profiled else None,
        }