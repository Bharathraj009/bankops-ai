package com.bankops.banking;

import com.bankops.banking.security.ApiSecurityFilter;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;

class ApiSecurityFilterTests {
    private static final String TOKEN = "isolated-security-regression-token-only";
    private MockHttpServletResponse call(ApiSecurityFilter filter, String path, String header, String value) throws Exception {
        var request = new MockHttpServletRequest("POST", path);
        request.addHeader("Host", "localhost");
        if (header != null) request.addHeader(header, value);
        var response = new MockHttpServletResponse();
        filter.doFilter(request, response, (req,res) -> ((MockHttpServletResponse)res).setStatus(204));
        return response;
    }
    @Test void tokenIsRequiredBeforeAnyFinancialHandlerRuns() throws Exception {
        var filter = new ApiSecurityFilter(new MockEnvironment(), TOKEN, "localhost", "127.0.0.1");
        assertEquals(401, call(filter,"/api/v1/transfers",null,null).getStatus());
        assertEquals(401, call(filter,"/api/v1/accounts","Authorization","Bearer wrong").getStatus());
        assertEquals(204, call(filter,"/api/v1/transfers","Authorization","Bearer "+TOKEN).getStatus());
        assertEquals(401, call(filter,"/api/v1;parameter/accounts",null,null).getStatus());
        var contextual=new MockHttpServletRequest("POST","/bank/api/v1/accounts");
        contextual.setContextPath("/bank"); contextual.addHeader("Host","localhost");
        var denied=new MockHttpServletResponse();
        filter.doFilter(contextual,denied,(req,res)->fail("Must reject before routing"));
        assertEquals(401,denied.getStatus());
        assertEquals("no-store",call(filter,"/actuator/health",null,null).getHeader("Cache-Control"));
    }
    @Test void productionAndNetworkBindingFailClosedWithoutCredential() throws Exception {
        var env = new MockEnvironment();env.setActiveProfiles("production");
        assertEquals(503,call(new ApiSecurityFilter(env,"","localhost","127.0.0.1"),"/api/v1/accounts",null,null).getStatus());
        env = new MockEnvironment();env.setActiveProfiles("dev");
        assertEquals(503,call(new ApiSecurityFilter(env,"","localhost","0.0.0.0"),"/api/v1/dev/accounts/x/fund",null,null).getStatus());
    }
    @Test void originAndFetchMetadataBlockCrossSiteWrites() throws Exception {
        var filter = new ApiSecurityFilter(new MockEnvironment(),"","localhost","127.0.0.1");
        for (String origin:new String[]{"null","https://attacker.invalid","http://localhost@attacker.invalid","http://localhost?x=1"})
            assertEquals(403,call(filter,"/api/v1/transfers","Origin",origin).getStatus());
        assertEquals(403,call(filter,"/api/v1/accounts","Sec-Fetch-Site","cross-site").getStatus());
        assertEquals(503,call(filter,"/api/v1/accounts","Origin","http://localhost").getStatus());
    }
}
