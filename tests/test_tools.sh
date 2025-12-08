#!/bin/bash

# Variables para conteo de pruebas
TOTAL_TESTS=11
PASSED_TESTS=0
FAILED_TESTS=0
TEST_RESULTS=()
BASE_URL="http://localhost:8009"

# Función para mostrar resultados y pausar
show_result() {
    local test_name="$1"
    local result="$2"

    if [[ $result -eq 0 ]]; then
        echo "✅ $test_name: EXITOSO"
        ((PASSED_TESTS++))
        TEST_RESULTS+=("✅ $test_name")
    else
        echo "❌ $test_name: FALLÓ"
        ((FAILED_TESTS++))
        TEST_RESULTS+=("❌ $test_name")
    fi

    echo ""
    echo "📋 Presiona Enter para continuar..."
    read
}

# Función para validar respuestas JSON
validate_json_response() {
    local response="$1"
    local expected_fields="$2"

    if [[ -z "$response" ]]; then
        echo "❌ Respuesta vacía"
        return 1
    fi

    # Verificar si es JSON válido
    if echo "$response" | python3 -m json.tool >/dev/null 2>&1; then
        echo "✅ JSON válido recibido"

        # Verificar campos esperados si se proporcionan
        if [[ -n "$expected_fields" ]]; then
            IFS=',' read -ra FIELDS <<< "$expected_fields"
            for field in "${FIELDS[@]}"; do
                if echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); exit(0 if '$field' in str(data) else 1)" 2>/dev/null; then
                    echo "✅ Campo '$field' encontrado"
                else
                    echo "⚠️  Campo '$field' no encontrado"
                fi
            done
        fi
        return 0
    else
        echo "❌ Respuesta no es JSON válido: $response"
        return 1
    fi
}

# Función para ejecutar pruebas con SSE usando curl -N
test_with_sse() {
    local url="$1"
    local description="$2"
    local timeout="${3:-10}"

    echo "🔄 Iniciando conexión SSE..."
    echo "🌐 URL: $url"
    echo "⏱️ Timeout: ${timeout}s"
    echo ""

    # Crear archivo temporal para capturar la salida
    local temp_file=$(mktemp)

    # Ejecutar curl con timeout y capturar salida
    timeout $timeout curl -N -s "$url" > "$temp_file" &
    local curl_pid=$!

    echo "📡 Conectando... (PID: $curl_pid)"

    # Esperar más tiempo para que se procesen todas las tareas (incluyendo fuzzy search)
    echo "⏳ Esperando que se procesen todas las tareas (incluyendo nuevas pruebas fuzzy)..."
    sleep 8

    # Verificar si el proceso sigue corriendo
    if kill -0 $curl_pid 2>/dev/null; then
        echo "✅ Conexión SSE activa, recibiendo datos..."

        # Esperar un poco más para capturar todos los resultados fuzzy
        sleep 5

        # Mostrar todos los datos recibidos
        echo "📊 Datos SSE recibidos:"
        if [[ -s "$temp_file" ]]; then
            cat "$temp_file" | while read line; do
                if [[ -n "$line" ]]; then
                    echo "   📄 $line"
                fi
            done
        fi

        # Terminar el proceso curl
        kill $curl_pid 2>/dev/null
        wait $curl_pid 2>/dev/null

        # Verificar si se recibieron datos
        if [[ -s "$temp_file" ]]; then
            echo "✅ Datos SSE recibidos correctamente"
            rm "$temp_file"
            return 0
        else
            echo "❌ No se recibieron datos SSE"
            rm "$temp_file"
            return 1
        fi
    else
        echo "❌ Conexión SSE falló"
        rm "$temp_file"
        return 1
    fi
}

# Función para ejecutar pruebas POST con validación mejorada
test_post_request() {
    local url="$1"
    local data="$2"
    local description="$3"
    local expected_fields="$4"

    echo "📤 Enviando petición POST..."
    echo "🌐 URL: $url"
    echo "📝 Descripción: $description"
    echo ""

    # Ejecutar la petición y capturar respuesta
    local response=$(curl -s -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "$data")
    local curl_result=$?

    if [[ $curl_result -eq 0 ]]; then
        echo "📊 Respuesta recibida:"
        echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        echo ""

        # Validar la respuesta
        validate_json_response "$response" "$expected_fields"
        return $?
    else
        echo "❌ Error en la petición HTTP"
        return 17
    fi
}

# Función para verificar si el servidor está activo
check_server_health() {
    echo "🔍 Verificando estado del servidor MCP..."

    local response=$(curl -s -w "%{http_code}" "$BASE_URL/health" 2>/dev/null)
    local http_code="${response: -3}"
    local body="${response%???}"

    if [[ "$http_code" == "200" ]] && [[ "$body" == *"ok"* ]]; then
        echo "✅ Servidor MCP está activo y respondiendo correctamente"
        return 0
    else
        echo "❌ Servidor MCP no está disponible"
        return 1
    fi
}

# Función para intentar iniciar el servidor
start_server() {
    echo "🚀 Intentando iniciar el servidor MCP..."

    # Buscar el directorio del servidor
    if [[ -f "../server.py" ]]; then
        echo "📁 Encontrado server.py en directorio padre"
        cd ..
        echo "⚡ Iniciando servidor en background..."
        python server.py --port 8009 &
        SERVER_PID=$!
        echo "📋 PID del servidor: $SERVER_PID"
        cd test

        # Esperar un momento para que el servidor arranque
        echo "⏳ Esperando que el servidor arranque (10 segundos)..."
        sleep 10

        return 0
    elif [[ -f "server.py" ]]; then
        echo "📁 Encontrado server.py en directorio actual"
        echo "⚡ Iniciando servidor en background..."
        python server.py --port 8009 &
        SERVER_PID=$!
        echo "📋 PID del servidor: $SERVER_PID"

        # Esperar un momento para que el servidor arranque
        echo "⏳ Esperando que el servidor arranque (10 segundos)..."
        sleep 10

        return 0
    else
        echo "❌ No se pudo encontrar server.py"
        return 1
    fi
}

# Función para mostrar instrucciones manuales
show_manual_instructions() {
    echo ""
    echo "🔧 === INSTRUCCIONES PARA INICIAR EL SERVIDOR === 🔧"
    echo "📝 No se pudo iniciar automáticamente el servidor MCP"
    echo ""
    echo "💡 Por favor ejecuta manualmente uno de estos comandos:"
    echo "   1️⃣  En el directorio raíz del proyecto:"
    echo "       cd .. && python server.py --port 8009"
    echo ""
    echo "   2️⃣  O si tienes un script de inicio:"
    echo "       ./start_server.sh"
    echo ""
    echo "   3️⃣  O usando uvicorn:"
    echo "       python server.py --port 8009"
    echo ""
    echo "🎯 El servidor debe estar disponible en: $BASE_URL"
    echo "🏥 Verifica con: curl $BASE_URL/health"
    echo ""
    echo "⏸️  Una vez iniciado el servidor, presiona Enter para continuar..."
    read
}

echo "🚀 === SUITE DE PRUEBAS MCP TOOLS === 🚀"
echo "📊 Ejecutando $TOTAL_TESTS pruebas del sistema MCP (SSE, Fuzzy Search, Unaccent)"
echo "🔗 URL Base: $BASE_URL"
echo ""

# Verificar si el servidor está activo
if ! check_server_health; then
    echo ""
    echo "🔄 Intentando iniciar el servidor automáticamente..."

    if start_server; then
        echo "⏳ Verificando nuevamente el estado del servidor..."
        sleep 2

        if check_server_health; then
            echo "🎉 ¡Servidor iniciado exitosamente!"
        else
            show_manual_instructions
            # Verificar una vez más después de las instrucciones manuales
            if ! check_server_health; then
                echo "❌ El servidor sigue sin responder. Abortando pruebas."
                exit 1
            fi
        fi
    else
        show_manual_instructions
        # Verificar una vez más después de las instrucciones manuales
        if ! check_server_health; then
            echo "❌ El servidor sigue sin responder. Abortando pruebas."
            exit 1
        fi
    fi
fi

echo ""
echo "✅ Servidor verificado - Iniciando pruebas..."
echo "═══════════════════════════════════════════════"
echo ""

# Prueba 1: Health Check
echo "🏥 === PRUEBA 1: VERIFICACIÓN DE SALUD === 🏥"
echo "📝 Descripción: Verifica que el servidor MCP esté funcionando correctamente"
echo "🎯 Objetivo: Obtener estado de salud del API"
echo ""

response=$(curl -s $BASE_URL/health)
curl_result=$?

if [[ $curl_result -eq 0 ]]; then
    echo "📊 Respuesta recibida:"
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    validate_json_response "$response" "status"
    RESULT1=$?
else
    echo "❌ Error en la petición HTTP"
    RESULT1=1
fi

show_result "Health Check" $RESULT1

# Prueba 2: Discovery de herramientas
echo "🔍 === PRUEBA 2: DESCUBRIMIENTO DE HERRAMIENTAS === 🔍"
echo "📝 Descripción: Obtiene la lista de todas las herramientas disponibles en MCP"
echo "🎯 Objetivo: Verificar que las herramientas estén registradas correctamente"
echo ""

response=$(curl -s $BASE_URL/tools)
curl_result=$?

if [[ $curl_result -eq 0 ]]; then
    echo "📊 Respuesta recibida:"
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    validate_json_response "$response" "tools"
    RESULT2=$?
else
    echo "❌ Error en la petición HTTP"
    RESULT2=1
fi

show_result "Discovery de herramientas" $RESULT2

# Prueba 3: Búsqueda por SKU
echo "🔎 === PRUEBA 3: BÚSQUEDA POR SKU === 🔎"
echo "📝 Descripción: Busca un producto específico usando su código SKU"
echo "🎯 Objetivo: Verificar la funcionalidad de búsqueda exacta por identificador"
echo "🏷️ SKU buscado: KITCH-0044"
echo ""

data='{
  "action": "fetch_by_sku",
  "id": "test-sku",
  "params": {
    "sku": "KITCH-0044"
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda por SKU" "status,id"
RESULT3=$?
show_result "Búsqueda por SKU" $RESULT3

# Prueba 4: Búsqueda por ID
echo "🆔 === PRUEBA 4: BÚSQUEDA POR ID === 🆔"
echo "📝 Descripción: Busca un producto usando su ID numérico en la base de datos"
echo "🎯 Objetivo: Verificar la funcionalidad de búsqueda por clave primaria"
echo "🔢 ID buscado: 1"
echo ""

data='{
  "action": "fetch_by_id",
  "id": "test-id",
  "params": {
    "id": 1
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda por ID" "status,id"
RESULT4=$?
show_result "Búsqueda por ID" $RESULT4

# Prueba 5: Búsqueda semántica
echo "🧠 === PRUEBA 5: BÚSQUEDA SEMÁNTICA === 🧠"
echo "📝 Descripción: Realiza búsqueda inteligente usando embeddings vectoriales"
echo "🎯 Objetivo: Verificar la funcionalidad de búsqueda por similitud semántica"
echo "💭 Query: 'licuadora'"
echo "📊 Resultados solicitados: 1"
echo ""

data='{
  "action": "search",
  "id": "test-search",
  "params": {
    "query": "licuadora",
    "k": 1
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda semántica" "status,id"
RESULT5=$?
show_result "Búsqueda semántica" $RESULT5

# Prueba 6: Fuzzy Search Names
echo "🔍 === PRUEBA 6: BÚSQUEDA FUZZY POR NOMBRES === 🔍"
echo "📝 Descripción: Búsqueda tolerante a errores en nombres de productos"
echo "🎯 Objetivo: Verificar detección de similitud y corrección de errores tipográficos"
echo "💭 Query: 'licuadora' (producto existente)"
echo "🎛️ Threshold: 40% (optimizado para nombres)"
echo ""

data='{
  "action": "fuzzy_search_names",
  "id": "test-fuzzy-names",
  "params": {
    "query": "licuadora",
    "limit": 3
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda fuzzy por nombres" "status,id"
RESULT6=$?
show_result "Búsqueda Fuzzy Names" $RESULT6

# Prueba 7: Fuzzy Search Comprehensive con Typo
echo "🧠 === PRUEBA 7: BÚSQUEDA FUZZY COMPRENSIVA (TYPO) === 🧠"
echo "📝 Descripción: Búsqueda tolerante a errores en múltiples campos"
echo "🎯 Objetivo: Detectar errores tipográficos en búsquedas multi-campo"
echo "💭 Query: 'auricuares' (typo de 'auriculares')"
echo "📊 Campos: name, description, brand, category"
echo "🎛️ Threshold: 25% (más tolerante para detección amplia)"
echo ""

data='{
  "action": "fuzzy_search_comprehensive",
  "id": "test-fuzzy-comprehensive",
  "params": {
    "query": "auricuares",
    "limit": 2
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda fuzzy comprensiva" "status,id"
RESULT7=$?
show_result "Búsqueda Fuzzy Comprehensive" $RESULT7

# Prueba 8: Fuzzy Search Custom Parameters
echo "⚙️ === PRUEBA 8: BÚSQUEDA FUZZY PERSONALIZADA === ⚙️"
echo "📝 Descripción: Búsqueda fuzzy con parámetros personalizables"
echo "🎯 Objetivo: Probar control granular de similitud y campos"
echo "💭 Query: 'compu' (parcial de 'computación')"
echo "📊 Campos específicos: ['name', 'category']"
echo "🎛️ Threshold personalizado: 20%"
echo "📋 Límite: 3 resultados"
echo ""

data='{
  "action": "fuzzy_search",
  "id": "test-fuzzy-custom",
  "params": {
    "query": "compu",
    "fields": ["name", "category"],
    "min_similarity": 0.20,
    "limit": 3,
    "include_similarity": true
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda fuzzy personalizada" "status,id"
RESULT8=$?
show_result "Búsqueda Fuzzy Custom" $RESULT8

# Prueba 9: Búsqueda Accent-Insensitive (unaccent)
echo "🆕 === PRUEBA 9: BÚSQUEDA ACCENT-INSENSITIVE (UNACCENT) === 🆕"
echo "📝 Descripción: Verifica que unaccent permite buscar sin tildes"
echo "🎯 Objetivo: Demostrar que 'camara' encuentra 'cámara'"
echo "🔍 Query sin tildes: 'camara' (buscará productos con tildes)"
echo "🌍 Unicode: Accent/case-insensitive search"
echo "✨ Magia: normalize_text() convierte 'Cámara' -> 'camara'"
echo ""

data='{
  "action": "fuzzy_search",
  "id": "test-unaccent",
  "params": {
    "query": "camara",
    "fields": ["name"],
    "min_similarity": 0.3,
    "limit": 5,
    "include_similarity": true
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda accent-insensitive" "status,id"
RESULT9=$?
show_result "Búsqueda Accent-Insensitive" $RESULT9

# Prueba 10: Búsqueda Smart con Typos (fuzzy_search_smart)
echo "🧠 === PRUEBA 10: BÚSQUEDA SMART CON TYPOS === 🧠"
echo "📝 Descripción: Búsqueda inteligente con estrategia multi-nivel para tolerar errores"
echo "🎯 Objetivo: Encontrar 'cargador' aunque se escriba 'cargaores' (con typo)"
echo "📊 Estrategia: 3 niveles - similarity, word_similarity, fallback"
echo ""

data='{
  "action": "fuzzy_search_smart",
  "id": "test-smart-typo",
  "params": {
    "query": "cargaores",
    "fields": ["name"],
    "limit": 5,
    "strict_threshold": 0.3,
    "word_threshold": 0.4,
    "fallback_threshold": 0.2
  }
}'

test_post_request "$BASE_URL/invoke" "$data" "Búsqueda smart con typo 'cargaores'" "status,id"
RESULT10=$?
show_result "Búsqueda smart con typos" $RESULT10

# Dar tiempo para procesar
sleep 2
echo ""
echo "Presiona Enter para continuar..."
read

# Prueba 11: Conexión SSE (FINAL)
echo "📡 === PRUEBA 11: CONEXIÓN SSE (SERVER-SENT EVENTS) === 📡"
echo "📝 Descripción: Verifica streaming de resultados de todas las pruebas anteriores"
echo "🎯 Objetivo: Conectar al endpoint SSE y recibir eventos acumulados"
echo "🔄 Usando: curl -N para mantener conexión persistente"
echo "⚠️  IMPORTANTE: Esta prueba mostrará resultados de todas las operaciones previas"
echo ""

test_with_sse "$BASE_URL/sse" "Conexión SSE" 20
RESULT11=$?
show_result "Conexión SSE (Final)" $RESULT11

# Resumen final
echo "🎉 === RESUMEN FINAL DE PRUEBAS === 🎉"
echo "═══════════════════════════════════════"
echo "📊 Total de pruebas ejecutadas: 11"
echo "✅ Pruebas exitosas: $PASSED_TESTS"
echo "❌ Pruebas fallidas: $FAILED_TESTS"
echo ""
echo "📋 Detalle de resultados:"
for result in "${TEST_RESULTS[@]}"; do
    echo "   $result"
done
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo "🏆 ¡TODAS LAS PRUEBAS PASARON EXITOSAMENTE! 🏆"
    echo "🎯 El sistema MCP está funcionando correctamente"
    exit 0
else
    echo "⚠️  ALGUNAS PRUEBAS FALLARON ⚠️"
    echo "🔧 Revisa los logs para más detalles"
    exit 1
fi