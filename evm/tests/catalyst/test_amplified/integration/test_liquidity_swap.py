import brownie
import pytest
from brownie import ZERO_ADDRESS, chain, convert, reverts, web3
from brownie.test import given, strategy
import tests.catalyst.utils.pool_utils as pool_utils
from math import inf

pytestmark = pytest.mark.usefixtures("group_finish_setup", "group_connect_pools")


@pytest.mark.no_call_coverage
@given(deposit_percentage=strategy("uint256", max_value=20000), swap_percentage=strategy("uint256", max_value=10000))
def test_liquidity_swap(
    channel_id,
    pool_1,
    pool_2,
    pool_1_tokens,
    get_pool_2_weights,
    get_pool_2_balances,
    get_pool_2_unit_tracker,
    get_pool_2_amp,
    berg,
    deployer,
    ibc_emulator,
    compute_expected_liquidity_swap,
    swap_percentage,
    deposit_percentage
    ):
    swap_percentage /= 10000
    deposit_percentage /= 10000
    
    deposit_amounts = [int(token.balanceOf(pool_1) * deposit_percentage) for token in pool_1_tokens]
    [token.transfer(berg, amount, {'from': deployer}) for amount, token in zip(deposit_amounts, pool_1_tokens)]
    [token.approve(pool_1, amount, {'from': berg}) for amount, token in zip(deposit_amounts, pool_1_tokens)]
    
    estimatedPoolTokens = int(pool_1.totalSupply()*deposit_percentage)
    
    tx = pool_1.depositMixed(deposit_amounts, int(estimatedPoolTokens*0.999), {"from": berg})
    
    pool1_tokens = tx.return_value
    
    pool1_tokens_swapped = int(pool1_tokens * swap_percentage)
    
    computation = compute_expected_liquidity_swap(pool1_tokens_swapped)
    U, estimatedPool2Tokens = computation["U"], computation["output"]
    
    tx = pool_1.outLiquidity(
        channel_id,
        convert.to_bytes(pool_2.address.replace("0x", "")),
        convert.to_bytes(berg.address.replace("0x", "")),
        pool1_tokens_swapped,
        int(estimatedPool2Tokens*9/10),
        berg,
        {"from": berg}
    )
    assert pool_1.balanceOf(berg) == pool1_tokens - pool1_tokens_swapped
    
    b0_times_n = len(pool_1_tokens) * pool_utils.compute_balance_0(get_pool_2_weights(), get_pool_2_balances(), get_pool_2_unit_tracker(), get_pool_2_amp())
    
    U = tx.events["SwapToLiquidityUnits"]["output"]
    expectedB0 = 2**256
    if int(int(b0_times_n)**(1 - get_pool_2_amp()/10**18)) >= int(U/10**18):
        expectedB0 = pool_utils.compute_expected_swap_given_U(U, 1, b0_times_n, get_pool_2_amp())
        
        
    if (pool_2.getUnitCapacity() < expectedB0):
        with reverts("Swap exceeds security limit"):
            txe = ibc_emulator.execute(tx.events["IncomingMetadata"]["metadata"][0], tx.events["IncomingPacket"]["packet"], {"from": berg})
        
        return
    else:
        txe = ibc_emulator.execute(tx.events["IncomingMetadata"]["metadata"][0], tx.events["IncomingPacket"]["packet"], {"from": berg})
    
    purchased_tokens = txe.events["SwapFromLiquidityUnits"]["output"]
    
    assert purchased_tokens == pool_2.balanceOf(berg)
    
    
    assert purchased_tokens <= int(estimatedPool2Tokens*1.000001), "Swap returns more than theoretical"
    
    if swap_percentage < 1e-05:
        return
    
    assert (estimatedPool2Tokens * 9 /10) <= purchased_tokens, "Swap returns less than 9/10 theoretical"
    

