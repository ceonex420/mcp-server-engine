#!/bin/bash

# Script para monitorear logs del servidor MCP en tiempo real
# Muestra logs de todos los componentes de manera organizada

echo "=========================================="
echo "Monitor de Logs MCP Server"
echo "=========================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

LOGS_DIR="../logs"

# Verificar que existe el directorio de logs
if [ ! -d "$LOGS_DIR" ]; then
    echo -e "${RED}❌ No se encontró el directorio de logs: $LOGS_DIR${NC}"
    echo "   Asegúrate de que el servidor esté corriendo o haya corrido al menos una vez"
    exit 1
fi

# Función para mostrar opciones
show_menu() {
    echo "Opciones de monitoreo:"
    echo "1. 📊 Ver logs del servidor principal (mcp_official_server.log)"
    echo "2. 🔍 Ver logs de búsqueda fuzzy (mcp_tools_fuzzy_search.log)"
    echo "3. 🗄️  Ver logs de base de datos (mcp_db.log)"
    echo "4. 🎯 Ver logs de fetch (mcp_tools_fetch.log)"
    echo "5. 🧠 Ver logs de embeddings (mcp_embeddings.log)"
    echo "6. 📄 Ver TODOS los logs en tiempo real"
    echo "7. 🗑️  Limpiar archivos de log"
    echo "8. 📋 Ver resumen de errores"
    echo "0. Salir"
    echo ""
}

# Función para seguir un log específico
tail_log() {
    local logfile="$1"
    local color="$2"
    local name="$3"

    if [ -f "$LOGS_DIR/$logfile" ]; then
        echo -e "${color}>>> Monitoreando $name (Ctrl+C para salir)${NC}"
        echo ""
        tail -f "$LOGS_DIR/$logfile" | while read line; do
            echo -e "${color}[$name]${NC} $line"
        done
    else
        echo -e "${RED}❌ No se encontró el archivo: $LOGS_DIR/$logfile${NC}"
    fi
}

# Función para ver todos los logs
tail_all_logs() {
    echo -e "${CYAN}>>> Monitoreando TODOS los logs (Ctrl+C para salir)${NC}"
    echo ""

    # Usar multitail si está disponible, sino usar tail básico
    if command -v multitail >/dev/null 2>&1; then
        multitail \
            -ci green "$LOGS_DIR/mcp_official_server.log" \
            -ci blue "$LOGS_DIR/mcp_tools_fuzzy_search.log" \
            -ci yellow "$LOGS_DIR/mcp_db.log" \
            -ci magenta "$LOGS_DIR/mcp_tools_fetch.log" \
            -ci cyan "$LOGS_DIR/mcp_embeddings.log"
    else
        # Fallback usando tail básico
        tail -f "$LOGS_DIR"/*.log 2>/dev/null | while read line; do
            # Detectar qué archivo y colorear
            if [[ $line == *"mcp_official_server"* ]]; then
                echo -e "${GREEN}[SERVER]${NC} $line"
            elif [[ $line == *"mcp_tools_fuzzy_search"* ]]; then
                echo -e "${BLUE}[FUZZY]${NC} $line"
            elif [[ $line == *"mcp_db"* ]]; then
                echo -e "${YELLOW}[DB]${NC} $line"
            elif [[ $line == *"mcp_tools_fetch"* ]]; then
                echo -e "${MAGENTA}[FETCH]${NC} $line"
            elif [[ $line == *"mcp_embeddings"* ]]; then
                echo -e "${CYAN}[EMBED]${NC} $line"
            else
                echo "$line"
            fi
        done
    fi
}

# Función para limpiar logs
clean_logs() {
    echo -e "${YELLOW}⚠️  ¿Estás seguro de que quieres limpiar todos los logs? (y/N)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -f "$LOGS_DIR"/*.log
        echo -e "${GREEN}✅ Logs limpiados${NC}"
    else
        echo "Operación cancelada"
    fi
}

# Función para mostrar resumen de errores
show_error_summary() {
    echo -e "${RED}📋 Resumen de errores en logs:${NC}"
    echo ""

    for logfile in "$LOGS_DIR"/*.log; do
        if [ -f "$logfile" ]; then
            filename=$(basename "$logfile")
            error_count=$(grep -c -i "error\|exception\|failed\|critical" "$logfile" 2>/dev/null || echo "0")
            warning_count=$(grep -c -i "warning\|warn" "$logfile" 2>/dev/null || echo "0")

            if [ "$error_count" -gt 0 ] || [ "$warning_count" -gt 0 ]; then
                echo -e "${YELLOW}📁 $filename:${NC}"
                [ "$error_count" -gt 0 ] && echo -e "   ${RED}❌ Errores: $error_count${NC}"
                [ "$warning_count" -gt 0 ] && echo -e "   ${YELLOW}⚠️  Warnings: $warning_count${NC}"
                echo ""
            fi
        fi
    done
}

# Main loop
while true; do
    echo ""
    show_menu
    read -p "Selecciona una opción: " choice
    echo ""

    case $choice in
        1)
            tail_log "mcp_official_server.log" "$GREEN" "SERVER"
            ;;
        2)
            tail_log "mcp_tools_fuzzy_search.log" "$BLUE" "FUZZY"
            ;;
        3)
            tail_log "mcp_db.log" "$YELLOW" "DB"
            ;;
        4)
            tail_log "mcp_tools_fetch.log" "$MAGENTA" "FETCH"
            ;;
        5)
            tail_log "mcp_embeddings.log" "$CYAN" "EMBED"
            ;;
        6)
            tail_all_logs
            ;;
        7)
            clean_logs
            ;;
        8)
            show_error_summary
            read -p "Presiona Enter para continuar..."
            ;;
        0)
            echo "Saliendo del monitor de logs..."
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Opción no válida${NC}"
            ;;
    esac
done