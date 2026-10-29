package com.bankops.banking.dev;

import com.bankops.banking.transfer.dto.TransferResponse;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("dev & !prod & !production & !test")
@RequestMapping("/api/v1/dev/accounts")
public class DevFundingController {
    private final DevFundingService service;
    public DevFundingController(DevFundingService service) { this.service=service; }
    @PostMapping("/{accountId}/fund")
    public ResponseEntity<TransferResponse> fund(@PathVariable UUID accountId,
        @RequestHeader("Idempotency-Key") String key, @Valid @RequestBody FundingRequest request) {
        var result=service.fund(accountId,key,request.amount());
        return ResponseEntity.status(result.executed()?HttpStatus.CREATED:HttpStatus.OK).body(TransferResponse.from(result.transfer()));
    }
}
