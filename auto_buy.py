#!/usr/bin/env python3
"""
Auto Buy Script - Binance Spot Market Orders
=============================================
Script de CLI interactivo para distribuir capital en USDC según estrategias de inversión.

Autor: Francio - Algorithmic Finance
Fecha: Enero 2026
"""

import os
import sys
import logging
from decimal import Decimal, ROUND_DOWN
from typing import Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException


# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================

def setup_logging() -> logging.Logger:
    """
    Configura el sistema de logging con salida a consola y archivo.
    
    Returns:
        logging.Logger: Logger configurado para la aplicación.
    """
    logger = logging.getLogger("AutoBuy")
    logger.setLevel(logging.DEBUG)
    
    # Formato de logs
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Handler para archivo
    file_handler = logging.FileHandler("trading.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logging()


# =============================================================================
# DEFINICIÓN DE ESTRATEGIAS
# =============================================================================

@dataclass
class TokenSelection:
    """Representa un token seleccionado con su porcentaje de distribución."""
    token: str
    distribution_percentage: float  # Porcentaje de la categoría asignado a este token (0-100)


@dataclass
class CategoryAllocation:
    """Representa una categoría de inversión dentro de una estrategia."""
    name: str
    percentage: float
    options: list[str]
    selected_tokens: list[TokenSelection] = field(default_factory=list)


@dataclass
class InvestmentStrategy:
    """Representa una estrategia de inversión completa."""
    name: str
    categories: list[CategoryAllocation] = field(default_factory=list)
    
    def get_total_percentage(self) -> float:
        """Retorna el porcentaje total de la estrategia."""
        return sum(cat.percentage for cat in self.categories)


def get_strategies() -> dict[str, InvestmentStrategy]:
    """
    Define las estrategias de inversión disponibles.
    
    Returns:
        dict[str, InvestmentStrategy]: Diccionario con las estrategias disponibles.
    """
    strategies = {
        "moderada": InvestmentStrategy(
            name="Moderada",
            categories=[
                CategoryAllocation(
                    name="Bitcoin",
                    percentage=30.0,
                    options=["BTC"]
                ),
                CategoryAllocation(
                    name="Ethereum",
                    percentage=30.0,
                    options=["ETH"]
                ),
                CategoryAllocation(
                    name="Tokens Nativos",
                    percentage=20.0,
                    options=["ADA", "XRP"]
                ),
                CategoryAllocation(
                    name="Token Protocolo",
                    percentage=10.0,
                    options=["CAKE", "GRT"]
                ),
                CategoryAllocation(
                    name="StableCoin",
                    percentage=10.0,
                    options=["USDC", "PAXG"]
                ),
            ]
        ),
        "conservadora": InvestmentStrategy(
            name="Conservadora",
            categories=[
                CategoryAllocation(
                    name="Bitcoin",
                    percentage=50.0,
                    options=["BTC"]
                ),
                CategoryAllocation(
                    name="Ethereum",
                    percentage=20.0,
                    options=["ETH"]
                ),
                CategoryAllocation(
                    name="StableCoin",
                    percentage=30.0,
                    options=["USDC", "PAXG"]
                ),
            ]
        ),
    }
    
    return strategies


# =============================================================================
# CLIENTE DE BINANCE
# =============================================================================

class BinanceTrader:
    """
    Clase para manejar operaciones de trading en Binance Spot.
    
    Attributes:
        client (Client): Cliente de python-binance.
        base_asset (str): Activo base para trading (USDC).
        symbol_info_cache (dict): Cache de información de símbolos.
    """
    
    BASE_ASSET = "USDC"
    
    def __init__(self, api_key: str, api_secret: str) -> None:
        """
        Inicializa el cliente de Binance.
        
        Args:
            api_key: API Key de Binance.
            api_secret: API Secret de Binance.
        """
        logger.info("Conectando con Binance API...")
        self.client = Client(api_key, api_secret)
        self.symbol_info_cache: dict = {}
        self._validate_connection()
        logger.info("✅ Conexión establecida exitosamente.")
    
    def _validate_connection(self) -> None:
        """Valida la conexión con Binance obteniendo el estado del servidor."""
        try:
            status = self.client.get_system_status()
            if status.get("status") != 0:
                logger.warning("⚠️ Binance reporta estado de mantenimiento.")
        except BinanceAPIException as e:
            logger.error(f"Error al validar conexión: {e.message}")
            raise
    
    def get_usdc_balance(self) -> Decimal:
        """
        Obtiene el saldo disponible de USDC en la wallet Spot.
        
        Returns:
            Decimal: Saldo disponible de USDC.
        """
        try:
            account = self.client.get_account()
            for balance in account["balances"]:
                if balance["asset"] == self.BASE_ASSET:
                    free_balance = Decimal(balance["free"])
                    logger.info(f"💰 Saldo disponible USDC: {free_balance:.2f}")
                    return free_balance
            return Decimal("0")
        except BinanceAPIException as e:
            logger.error(f"Error al obtener saldo: {e.message}")
            raise
    
    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """
        Obtiene información del símbolo incluyendo filtros de trading.
        
        Args:
            symbol: Par de trading (ej. BTCUSDC).
            
        Returns:
            dict: Información del símbolo o None si no existe.
        """
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]
        
        try:
            info = self.client.get_symbol_info(symbol)
            if info:
                self.symbol_info_cache[symbol] = info
            return info
        except BinanceAPIException as e:
            logger.error(f"Error al obtener info de {symbol}: {e.message}")
            return None
    
    def get_min_notional(self, symbol: str) -> Decimal:
        """
        Obtiene el valor mínimo de orden (MIN_NOTIONAL) para un símbolo.
        
        Args:
            symbol: Par de trading.
            
        Returns:
            Decimal: Valor mínimo de orden en USDC.
        """
        info = self.get_symbol_info(symbol)
        if not info:
            return Decimal("10")  # Valor por defecto conservador
        
        for filter_item in info.get("filters", []):
            if filter_item["filterType"] == "NOTIONAL":
                return Decimal(filter_item.get("minNotional", "10"))
            # Binance legacy filter
            if filter_item["filterType"] == "MIN_NOTIONAL":
                return Decimal(filter_item.get("minNotional", "10"))
        
        return Decimal("10")
    
    def get_lot_size_info(self, symbol: str) -> tuple[Decimal, Decimal, Decimal]:
        """
        Obtiene los parámetros de LOT_SIZE para un símbolo.
        
        Args:
            symbol: Par de trading.
            
        Returns:
            tuple: (minQty, maxQty, stepSize)
        """
        info = self.get_symbol_info(symbol)
        if not info:
            return Decimal("0.00001"), Decimal("99999999"), Decimal("0.00001")
        
        for filter_item in info.get("filters", []):
            if filter_item["filterType"] == "LOT_SIZE":
                return (
                    Decimal(filter_item["minQty"]),
                    Decimal(filter_item["maxQty"]),
                    Decimal(filter_item["stepSize"])
                )
        
        return Decimal("0.00001"), Decimal("99999999"), Decimal("0.00001")
    
    def adjust_quantity_to_lot_size(
        self, 
        quantity: Decimal, 
        step_size: Decimal
    ) -> Decimal:
        """
        Ajusta la cantidad según el stepSize del LOT_SIZE filter.
        
        Args:
            quantity: Cantidad original.
            step_size: Paso mínimo permitido.
            
        Returns:
            Decimal: Cantidad ajustada.
        """
        if step_size == 0:
            return quantity
        
        # Calcular precisión basada en step_size
        precision = abs(step_size.as_tuple().exponent)
        adjusted = (quantity / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
        return adjusted.quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN)
    
    def get_current_price(self, symbol: str) -> Decimal:
        """
        Obtiene el precio actual de un símbolo.
        
        Args:
            symbol: Par de trading.
            
        Returns:
            Decimal: Precio actual.
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return Decimal(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"Error al obtener precio de {symbol}: {e.message}")
            raise
    
    def validate_order(
        self, 
        symbol: str, 
        usdc_amount: Decimal
    ) -> tuple[bool, str, Decimal]:
        """
        Valida si una orden cumple con los filtros de Binance.
        
        Args:
            symbol: Par de trading.
            usdc_amount: Monto en USDC a invertir.
            
        Returns:
            tuple: (es_válida, mensaje, cantidad_ajustada)
        """
        min_notional = self.get_min_notional(symbol)
        
        if usdc_amount < min_notional:
            return (
                False, 
                f"❌ Monto {usdc_amount:.2f} USDC menor al mínimo requerido ({min_notional} USDC)",
                Decimal("0")
            )
        
        # Obtener precio actual y calcular cantidad
        current_price = self.get_current_price(symbol)
        raw_quantity = usdc_amount / current_price
        
        # Ajustar según LOT_SIZE
        min_qty, max_qty, step_size = self.get_lot_size_info(symbol)
        adjusted_quantity = self.adjust_quantity_to_lot_size(raw_quantity, step_size)
        
        if adjusted_quantity < min_qty:
            return (
                False,
                f"❌ Cantidad {adjusted_quantity} menor a minQty ({min_qty})",
                Decimal("0")
            )
        
        if adjusted_quantity > max_qty:
            return (
                False,
                f"❌ Cantidad {adjusted_quantity} mayor a maxQty ({max_qty})",
                Decimal("0")
            )
        
        return (True, "✅ Orden válida", adjusted_quantity)
    
    def execute_market_buy(
        self, 
        token: str, 
        usdc_amount: Decimal
    ) -> Optional[dict]:
        """
        Ejecuta una orden de compra MARKET.
        
        Args:
            token: Token a comprar (ej. BTC, ETH).
            usdc_amount: Monto en USDC a gastar.
            
        Returns:
            dict: Resultado de la orden o None si falla.
        """
        symbol = f"{token}{self.BASE_ASSET}"
        
        logger.info(f"📊 Preparando orden MARKET para {symbol}...")
        logger.debug(f"Monto objetivo: {usdc_amount:.4f} USDC")
        
        # Validar orden
        is_valid, message, quantity = self.validate_order(symbol, usdc_amount)
        
        if not is_valid:
            logger.warning(message)
            return None
        
        try:
            # Ejecutar orden de mercado usando quoteOrderQty para especificar monto en USDC
            order = self.client.order_market_buy(
                symbol=symbol,
                quoteOrderQty=float(usdc_amount.quantize(Decimal("0.01")))
            )
            
            executed_qty = order.get("executedQty", "0")
            cummulative_quote = order.get("cummulativeQuoteQty", "0")
            
            logger.info(
                f"✅ ORDEN EJECUTADA | {symbol} | "
                f"Cantidad: {executed_qty} | "
                f"Gastado: {cummulative_quote} USDC | "
                f"OrderID: {order['orderId']}"
            )
            
            return order
            
        except BinanceOrderException as e:
            logger.error(f"❌ Error en orden {symbol}: {e.message}")
            return None
        except BinanceAPIException as e:
            logger.error(f"❌ Error API en {symbol}: {e.message}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado en {symbol}: {str(e)}")
            return None


# =============================================================================
# LÓGICA DE INTERACCIÓN CON USUARIO
# =============================================================================

class UserInterface:
    """Clase para manejar la interacción con el usuario via CLI."""
    
    @staticmethod
    def print_header() -> None:
        """Imprime el encabezado del programa."""
        print("\n" + "=" * 60)
        print("🚀 AUTO BUY - Binance Spot Market Orders")
        print("=" * 60 + "\n")
    
    @staticmethod
    def get_investment_amount() -> Decimal:
        """
        Solicita al usuario el monto a invertir.
        
        Returns:
            Decimal: Monto en USDC a invertir.
        """
        while True:
            try:
                amount_str = input("💵 Ingrese el monto total a invertir (USDC): ").strip()
                amount = Decimal(amount_str)
                
                if amount <= 0:
                    print("❌ El monto debe ser mayor a 0.")
                    continue
                
                return amount
                
            except Exception:
                print("❌ Por favor ingrese un número válido.")
    
    @staticmethod
    def select_strategy_mode(
        strategies: dict[str, InvestmentStrategy]
    ) -> tuple[str, list[InvestmentStrategy]]:
        """
        Permite al usuario seleccionar una estrategia o el modo combinado.
        
        Args:
            strategies: Diccionario de estrategias disponibles.
            
        Returns:
            tuple: (modo, lista_de_estrategias)
                   modo: 'single' o 'combined'
                   lista_de_estrategias: Lista con 1 o 2 estrategias
        """
        print("\n📋 Estrategias disponibles:")
        print("-" * 40)
        
        strategy_keys = list(strategies.keys())
        for idx, (key, strategy) in enumerate(strategies.items(), 1):
            print(f"  [{idx}] {strategy.name}")
            for cat in strategy.categories:
                options_str = ", ".join(cat.options)
                print(f"      • {cat.name}: {cat.percentage}% ({options_str})")
            print()
        
        # Opción adicional: ambas estrategias
        print(f"  [3] 🔀 AMBAS ESTRATEGIAS (50% / 50%)")
        print("      Divide el capital en partes iguales entre Moderada y Conservadora")
        print("      Configura tokens para ambas y ejecuta todo en una sola operación")
        print()
        
        while True:
            try:
                choice = input("Seleccione estrategia (1, 2 o 3): ").strip()
                idx = int(choice)
                
                if idx == 3:
                    logger.info("📌 Modo combinado: Ambas estrategias (50/50)")
                    return ("combined", list(strategies.values()))
                elif 1 <= idx <= len(strategy_keys):
                    selected = strategies[strategy_keys[idx - 1]]
                    logger.info(f"📌 Estrategia seleccionada: {selected.name}")
                    return ("single", [selected])
                else:
                    print("❌ Opción inválida.")
                    
            except ValueError:
                print("❌ Por favor ingrese un número.")
    
    @staticmethod
    def select_tokens_for_category(category: CategoryAllocation) -> list[TokenSelection]:
        """
        Permite al usuario seleccionar uno o varios tokens con distribución personalizada.
        
        Args:
            category: Categoría con múltiples opciones.
            
        Returns:
            list[TokenSelection]: Lista de tokens seleccionados con su distribución.
        """
        if len(category.options) == 1:
            return [TokenSelection(token=category.options[0], distribution_percentage=100.0)]
        
        print(f"\n🔄 Categoría: {category.name} ({category.percentage}%)")
        print("   Opciones disponibles:")
        
        for idx, option in enumerate(category.options, 1):
            print(f"   [{idx}] {option}")
        
        # Preguntar si quiere distribuir entre varios tokens
        print("\n   ¿Cómo desea asignar esta categoría?")
        print("   [1] Seleccionar UN solo token (100%)")
        print("   [2] Distribuir entre VARIOS tokens")
        
        while True:
            mode_choice = input("   Seleccione modo (1 o 2): ").strip()
            if mode_choice in ["1", "2"]:
                break
            print("   ❌ Por favor ingrese 1 o 2.")
        
        if mode_choice == "1":
            # Modo: seleccionar un solo token
            while True:
                try:
                    choice = input(f"   Seleccione token para {category.name}: ").strip()
                    idx = int(choice) - 1
                    
                    if 0 <= idx < len(category.options):
                        selected = category.options[idx]
                        logger.info(f"   ✓ Seleccionado: {selected} (100%)")
                        return [TokenSelection(token=selected, distribution_percentage=100.0)]
                    else:
                        print("   ❌ Opción inválida.")
                        
                except ValueError:
                    print("   ❌ Por favor ingrese un número.")
        
        else:
            # Modo: distribuir entre varios tokens
            return UserInterface._select_multiple_tokens_with_distribution(category)
    
    @staticmethod
    def _select_multiple_tokens_with_distribution(
        category: CategoryAllocation
    ) -> list[TokenSelection]:
        """
        Permite seleccionar múltiples tokens y asignar porcentajes de distribución.
        
        Args:
            category: Categoría con opciones de tokens.
            
        Returns:
            list[TokenSelection]: Tokens seleccionados con distribución.
        """
        selections: list[TokenSelection] = []
        remaining_percentage = 100.0
        available_options = category.options.copy()
        
        print(f"\n   📊 Distribución para {category.name}:")
        print(f"   (El total debe sumar 100%)")
        
        while remaining_percentage > 0 and available_options:
            print(f"\n   Porcentaje restante por asignar: {remaining_percentage:.1f}%")
            print("   Tokens disponibles:")
            
            for idx, option in enumerate(available_options, 1):
                print(f"   [{idx}] {option}")
            
            # Seleccionar token
            while True:
                try:
                    choice = input("   Seleccione token: ").strip()
                    idx = int(choice) - 1
                    
                    if 0 <= idx < len(available_options):
                        selected_token = available_options[idx]
                        break
                    else:
                        print("   ❌ Opción inválida.")
                except ValueError:
                    print("   ❌ Por favor ingrese un número.")
            
            # Asignar porcentaje
            while True:
                try:
                    # Si es el último token disponible o el usuario lo desea, asignar el resto
                    if len(available_options) == 1:
                        pct = remaining_percentage
                        print(f"   Asignando automáticamente {pct:.1f}% a {selected_token}")
                    else:
                        pct_input = input(
                            f"   Porcentaje para {selected_token} "
                            f"(máx {remaining_percentage:.1f}%, 'r' para el resto): "
                        ).strip().lower()
                        
                        if pct_input == 'r':
                            pct = remaining_percentage
                        else:
                            pct = float(pct_input)
                    
                    if pct <= 0:
                        print("   ❌ El porcentaje debe ser mayor a 0.")
                        continue
                    
                    if pct > remaining_percentage:
                        print(f"   ❌ El porcentaje no puede superar {remaining_percentage:.1f}%")
                        continue
                    
                    # Agregar selección
                    selections.append(TokenSelection(token=selected_token, distribution_percentage=pct))
                    remaining_percentage -= pct
                    available_options.remove(selected_token)
                    
                    logger.info(f"   ✓ {selected_token}: {pct:.1f}%")
                    break
                    
                except ValueError:
                    print("   ❌ Por favor ingrese un número válido.")
            
            # Si quedan tokens y porcentaje, preguntar si continuar
            if remaining_percentage > 0 and available_options:
                continue_choice = input("   ¿Agregar otro token? (s/n): ").strip().lower()
                if continue_choice not in ["s", "si", "sí", "y", "yes"]:
                    # Asignar el resto al último token seleccionado
                    if selections:
                        selections[-1] = TokenSelection(
                            token=selections[-1].token,
                            distribution_percentage=selections[-1].distribution_percentage + remaining_percentage
                        )
                        logger.info(
                            f"   ✓ Resto ({remaining_percentage:.1f}%) asignado a {selections[-1].token}"
                        )
                        remaining_percentage = 0
        
        # Mostrar resumen de la distribución
        print(f"\n   📋 Distribución final para {category.name}:")
        for sel in selections:
            actual_pct = category.percentage * sel.distribution_percentage / 100
            print(f"      • {sel.token}: {sel.distribution_percentage:.1f}% ({actual_pct:.2f}% del total)")
        
        return selections
    
    @staticmethod
    def confirm_execution(allocations: list[tuple[str, Decimal]]) -> bool:
        """
        Muestra resumen y solicita confirmación antes de ejecutar.
        
        Args:
            allocations: Lista de (token, monto) a ejecutar.
            
        Returns:
            bool: True si el usuario confirma, False si cancela.
        """
        print("\n" + "=" * 60)
        print("📋 RESUMEN DE ÓRDENES A EJECUTAR")
        print("=" * 60)
        
        # Agrupar tokens iguales para mostrar consolidado
        consolidated: dict[str, Decimal] = {}
        for token, amount in allocations:
            if token in consolidated:
                consolidated[token] += amount
            else:
                consolidated[token] = amount
        
        total = Decimal("0")
        trade_count = 0
        
        for token, amount in sorted(consolidated.items(), key=lambda x: x[1], reverse=True):
            if token == "USDC":
                print(f"  💎 {token}: {amount:.2f} USDC (se mantiene, sin operación)")
            else:
                print(f"  • {token}: {amount:.2f} USDC")
                trade_count += 1
            total += amount
        
        print("-" * 40)
        print(f"  TOTAL: {total:.2f} USDC")
        print(f"  Órdenes a ejecutar: {trade_count}")
        print("=" * 60)
        
        while True:
            confirm = input("\n⚠️  ¿Confirmar ejecución? (s/n): ").strip().lower()
            if confirm in ["s", "si", "sí", "y", "yes"]:
                return True
            elif confirm in ["n", "no"]:
                return False
            else:
                print("Por favor responda 's' o 'n'.")


# =============================================================================
# ORQUESTADOR PRINCIPAL
# =============================================================================

class TradingOrchestrator:
    """
    Orquestador principal que coordina la ejecución del trading.
    
    Attributes:
        trader (BinanceTrader): Cliente de trading.
        ui (UserInterface): Interfaz de usuario.
    """
    
    def __init__(self, trader: BinanceTrader) -> None:
        """
        Inicializa el orquestador.
        
        Args:
            trader: Cliente de BinanceTrader configurado.
        """
        self.trader = trader
        self.ui = UserInterface()
    
    def calculate_allocations(
        self, 
        strategy: InvestmentStrategy, 
        total_amount: Decimal
    ) -> list[tuple[str, Decimal]]:
        """
        Calcula las asignaciones de capital según la estrategia.
        
        Soporta distribución entre múltiples tokens por categoría.
        
        Args:
            strategy: Estrategia de inversión.
            total_amount: Monto total a invertir.
            
        Returns:
            list: Lista de tuplas (token, monto).
        """
        allocations: list[tuple[str, Decimal]] = []
        
        print("\n" + "-" * 40)
        print(f"🎯 CONFIGURACIÓN DE TOKENS - {strategy.name}")
        print("-" * 40)
        
        for category in strategy.categories:
            # Seleccionar tokens (puede ser uno o varios con distribución)
            selected_tokens = self.ui.select_tokens_for_category(category)
            category.selected_tokens = selected_tokens
            
            # Calcular monto base de la categoría
            category_amount = total_amount * Decimal(str(category.percentage)) / Decimal("100")
            
            # Distribuir entre los tokens seleccionados
            for token_selection in selected_tokens:
                # Calcular monto para este token según su distribución dentro de la categoría
                token_amount = category_amount * Decimal(str(token_selection.distribution_percentage)) / Decimal("100")
                token_amount = token_amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                
                allocations.append((token_selection.token, token_amount))
        
        return allocations
    
    def calculate_combined_allocations(
        self,
        strategies: list[InvestmentStrategy],
        total_amount: Decimal
    ) -> list[tuple[str, Decimal]]:
        """
        Calcula asignaciones para múltiples estrategias dividiendo el capital 50/50.
        
        Args:
            strategies: Lista de estrategias a ejecutar.
            total_amount: Monto total a invertir.
            
        Returns:
            list: Lista de tuplas (token, monto) de todas las estrategias.
        """
        all_allocations: list[tuple[str, Decimal]] = []
        amount_per_strategy = total_amount / Decimal(str(len(strategies)))
        amount_per_strategy = amount_per_strategy.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        
        print("\n" + "=" * 60)
        print("🔀 MODO COMBINADO: Configuración de ambas estrategias")
        print(f"   Capital por estrategia: {amount_per_strategy:.2f} USDC (50% c/u)")
        print("=" * 60)
        
        for idx, strategy in enumerate(strategies, 1):
            print(f"\n{'─' * 60}")
            print(f"📊 ESTRATEGIA {idx}/{len(strategies)}: {strategy.name}")
            print(f"   Monto asignado: {amount_per_strategy:.2f} USDC")
            print(f"{'─' * 60}")
            
            strategy_allocations = self.calculate_allocations(strategy, amount_per_strategy)
            all_allocations.extend(strategy_allocations)
        
        return all_allocations
    
    def consolidate_allocations(
        self,
        allocations: list[tuple[str, Decimal]]
    ) -> list[tuple[str, Decimal]]:
        """
        Consolida asignaciones del mismo token sumando sus montos.
        
        Esto optimiza las órdenes cuando el mismo token aparece en
        múltiples estrategias o categorías.
        
        Args:
            allocations: Lista original de (token, monto).
            
        Returns:
            list: Lista consolidada de (token, monto).
        """
        consolidated: dict[str, Decimal] = {}
        
        for token, amount in allocations:
            if token in consolidated:
                consolidated[token] += amount
            else:
                consolidated[token] = amount
        
        # Convertir de vuelta a lista de tuplas
        result = [(token, amount) for token, amount in consolidated.items()]
        
        # Ordenar por monto descendente para ejecutar las órdenes más grandes primero
        result.sort(key=lambda x: x[1], reverse=True)
        
        # Log si hubo consolidación
        if len(result) < len(allocations):
            logger.info(
                f"🔄 Órdenes consolidadas: {len(allocations)} → {len(result)} "
                f"(tokens duplicados combinados)"
            )
        
        return result
    
    def validate_balance(self, total_amount: Decimal) -> bool:
        """
        Valida que el usuario tenga saldo suficiente.
        
        Args:
            total_amount: Monto total a invertir.
            
        Returns:
            bool: True si hay saldo suficiente.
        """
        balance = self.trader.get_usdc_balance()
        
        if balance < total_amount:
            logger.error(
                f"❌ Saldo insuficiente. "
                f"Disponible: {balance:.2f} USDC | "
                f"Requerido: {total_amount:.2f} USDC"
            )
            return False
        
        logger.info(f"✅ Saldo verificado. Disponible: {balance:.2f} USDC")
        return True
    
    def execute_orders(
        self, 
        allocations: list[tuple[str, Decimal]]
    ) -> dict[str, dict]:
        """
        Ejecuta las órdenes de compra.
        
        Args:
            allocations: Lista de (token, monto) a ejecutar.
            
        Returns:
            dict: Resultados de las órdenes por token.
        """
        results = {}
        
        print("\n" + "=" * 60)
        print("⚡ EJECUTANDO ÓRDENES")
        print("=" * 60 + "\n")
        
        for token, amount in allocations:
            # Manejar caso especial: USDC/USDC
            if token == "USDC":
                logger.info(
                    f"💎 USDC: Manteniendo {amount:.2f} USDC en saldo. "
                    f"No se requiere operación."
                )
                results[token] = {
                    "status": "skipped",
                    "reason": "Base asset - no trade needed",
                    "amount": float(amount)
                }
                continue
            
            # Ejecutar orden de mercado
            order = self.trader.execute_market_buy(token, amount)
            
            if order:
                results[token] = {
                    "status": "success",
                    "order_id": order["orderId"],
                    "executed_qty": order["executedQty"],
                    "spent_usdc": order["cummulativeQuoteQty"]
                }
            else:
                results[token] = {
                    "status": "failed",
                    "amount": float(amount)
                }
        
        return results
    
    def print_summary(self, results: dict[str, dict]) -> None:
        """
        Imprime resumen final de la ejecución.
        
        Args:
            results: Resultados de las órdenes.
        """
        print("\n" + "=" * 60)
        print("📊 RESUMEN FINAL")
        print("=" * 60)
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for token, result in results.items():
            status = result["status"]
            
            if status == "success":
                success_count += 1
                print(
                    f"  ✅ {token}: Comprado {result['executed_qty']} "
                    f"por {result['spent_usdc']} USDC"
                )
            elif status == "skipped":
                skipped_count += 1
                print(f"  💎 {token}: Mantenido ({result['reason']})")
            else:
                failed_count += 1
                print(f"  ❌ {token}: Falló - {result.get('amount', 0)} USDC")
        
        print("-" * 40)
        print(f"  Total exitosas: {success_count}")
        print(f"  Total omitidas: {skipped_count}")
        print(f"  Total fallidas: {failed_count}")
        print("=" * 60 + "\n")
        
        logger.info(
            f"Ejecución completada: {success_count} éxitos, "
            f"{skipped_count} omitidas, {failed_count} fallos"
        )
    
    def run(self) -> None:
        """Ejecuta el flujo completo del programa."""
        try:
            self.ui.print_header()
            
            # Obtener estrategias
            strategies = get_strategies()
            
            # Solicitar monto a invertir
            total_amount = self.ui.get_investment_amount()
            logger.info(f"💵 Monto a invertir: {total_amount} USDC")
            
            # Validar saldo
            if not self.validate_balance(total_amount):
                print("\n❌ Operación cancelada por saldo insuficiente.")
                return
            
            # Seleccionar modo de estrategia
            mode, selected_strategies = self.ui.select_strategy_mode(strategies)
            
            # Calcular asignaciones según el modo
            if mode == "combined":
                allocations = self.calculate_combined_allocations(
                    selected_strategies, total_amount
                )
            else:
                allocations = self.calculate_allocations(
                    selected_strategies[0], total_amount
                )
            
            # Confirmar ejecución
            if not self.ui.confirm_execution(allocations):
                logger.info("❌ Operación cancelada por el usuario.")
                print("\n❌ Operación cancelada.")
                return
            
            # Consolidar órdenes del mismo token antes de ejecutar
            consolidated = self.consolidate_allocations(allocations)
            
            # Ejecutar órdenes
            results = self.execute_orders(consolidated)
            
            # Mostrar resumen
            self.print_summary(results)
            
        except KeyboardInterrupt:
            logger.warning("\n⚠️ Operación interrumpida por el usuario (Ctrl+C)")
            print("\n\n⚠️ Operación interrumpida.")
        except Exception as e:
            logger.exception(f"Error fatal: {str(e)}")
            print(f"\n❌ Error fatal: {str(e)}")
            raise


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main() -> None:
    """Función principal del programa."""
    # Cargar variables de entorno
    load_dotenv()
    
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    
    if not api_key or not api_secret:
        logger.error("❌ API_KEY y API_SECRET deben estar configurados en el archivo .env")
        print("\n❌ Error: Configure API_KEY y API_SECRET en el archivo .env")
        print("   Ejemplo de .env:")
        print("   API_KEY=tu_api_key_aqui")
        print("   API_SECRET=tu_api_secret_aqui")
        sys.exit(1)
    
    try:
        # Inicializar cliente de trading
        trader = BinanceTrader(api_key, api_secret)
        
        # Ejecutar orquestador
        orchestrator = TradingOrchestrator(trader)
        orchestrator.run()
        
    except BinanceAPIException as e:
        logger.error(f"Error de Binance API: {e.message}")
        print(f"\n❌ Error de Binance: {e.message}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error inesperado: {str(e)}")
        print(f"\n❌ Error inesperado: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
