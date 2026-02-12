Un agente autónomo encargado de vigilar una "maquina" que a veces se rompe.

* El agente tiene que monitorizar sensores, detectar anomalias, consultar el manual técnico para ver que pasa y decidir si:
    1. Reparar (ejecutar comando)
    2. Escalar (avisar humano)

MCP: servidor simple que simule la máquina (expone herramientas como leer_temperatura, reiniciar_motor, inyectar_refrigerante).
RAG: PDF técnico de la máquina. El agente debe buscar informacion en el.
Agente: LangGraph