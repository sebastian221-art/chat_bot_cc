Un cliente de un centro comercial mandó esta foto de algo que quiere encontrar. Describe lo que ves para buscarlo en el directorio de locales.

- "que_es": qué es, en pocas palabras (ej. "tenis deportivos", "vestido largo de fiesta", "hamburguesa").
- "busqueda": 1 a 4 palabras en español para buscar en el directorio (ej. "tenis deportivos", "vestido", "hamburguesa", "gafas de sol").
- "color" y "estilo": cortos.
- "referencia_de_estilo": solo si el diseño tiene un detalle MUY icónico de una marca (ej. "3 franjas laterales, estilo Adidas"); si no, null. Es una referencia visual, no una confirmación de marca.
- "es_producto": false si la foto no muestra algo que se compre o se coma (una persona, un paisaje, un documento, un pantallazo).

Responde SOLO este JSON:
{"es_producto": true, "que_es": "...", "busqueda": "...", "color": "...", "estilo": "...", "referencia_de_estilo": null}